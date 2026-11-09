import streamlit as st
from services.gemini_service import recommend_playlist
from services.spotify_service import (
    SessionCacheHandler,
    create_oauth_manager,
    create_spotify_playlist,
    get_spotify_client,
    get_track_uris,
    new_oauth_state,
)

# 1. 페이지 기본 설정 및 헤더
st.set_page_config(
    page_title="AI Music Playlist Generator",
    page_icon="🎵",
    layout="wide"
)


# 2. 사용자별 Spotify OAuth (토큰은 각 사용자의 st.session_state에만 저장)
@st.cache_resource
def pending_oauth_states() -> set:
    """발급한 OAuth state 값 목록 (CSRF 방지). Spotify에서 돌아오면 새 세션이 열리므로 서버 단위로 보관."""
    return set()


cache_handler = SessionCacheHandler(st.session_state)
sp_oauth = create_oauth_manager(cache_handler)

# Spotify 인증 후 리다이렉트로 돌아온 경우: code를 이 세션의 토큰으로 교환
query = st.query_params
if "code" in query:
    returned_state = query.get("state")
    if returned_state and returned_state in pending_oauth_states():
        pending_oauth_states().discard(returned_state)
        try:
            sp_oauth.get_access_token(query["code"], as_dict=False, check_cache=False)
        except Exception as e:
            st.error(f"❌ Spotify 로그인 처리 실패: {e}")
    else:
        st.error("❌ 유효하지 않은 로그인 요청입니다. 다시 연결해 주세요.")
    st.query_params.clear()
elif "error" in query:
    st.warning("Spotify 계정 연결이 취소되었습니다.")
    st.query_params.clear()

st.title("🎵 AI 맞춤형 음악 플레이리스트 추천 & 자동 생성기")
st.caption("Gemini AI가 분위기와 청취 상황을 분석하여 나만의 플레이리스트를 큐레이팅하고, 실제 음악 앱 계정에 자동으로 생성해 드립니다.")

# 2. 세션 상태(Session State) 초기화 (화면 리렌더링 시 데이터 유지)
if "recommendation" not in st.session_state:
    st.session_state.recommendation = None
if "playlist_url" not in st.session_state:
    st.session_state.playlist_url = None

st.divider()

# 2-1. Spotify 계정 연결 상태 (추천 전에 연결: 인증 후 돌아오면 새 화면이 열리기 때문)
st.subheader("0. 🟢 Spotify 계정 연결")
spotify_client = get_spotify_client(sp_oauth)
if spotify_client:
    conn_col1, conn_col2 = st.columns([4, 1])
    try:
        display_name = spotify_client.current_user().get("display_name") or "Spotify 사용자"
    except Exception:
        display_name = "Spotify 사용자"
    conn_col1.success(f"✅ {display_name} 계정으로 연결됨")
    if conn_col2.button("연결 해제", use_container_width=True):
        cache_handler.clear()
        st.rerun()
else:
    if "oauth_state" not in st.session_state:
        st.session_state.oauth_state = new_oauth_state()
        pending_oauth_states().add(st.session_state.oauth_state)
    auth_url = sp_oauth.get_authorize_url(state=st.session_state.oauth_state)
    st.caption("플레이리스트를 내 계정에 저장하려면 먼저 연결해 주세요. (추천만 받을 때는 생략 가능)")
    st.link_button("Spotify 계정 연결하기", auth_url)

st.divider()

# 3. 폼 UI (요청사항 1 반영: 장르 선택, 분위기 슬라이더/텍스트, 상황 설명, 플랫폼 선택 드롭다운)
st.subheader("1. 🎧 음악 추천 조건 설정")

with st.form("playlist_input_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        # 장르 선택
        genre_option = st.selectbox(
            "선호 장르 선택",
            ["Indie Pop / Acoustic", "R&B / Soul", "Lo-Fi / Jazz", "Pop / Dance", "K-Pop", "Rock / Metal", "Hip-Hop", "직접 입력"]
        )
        if genre_option == "직접 입력":
            genre = st.text_input("장르 직접 입력", placeholder="예: Synthwave, City Pop")
        else:
            genre = genre_option
            
        # 음악 플랫폼 선택 드롭다운
        platform = st.selectbox(
            "연동할 음악 플랫폼 선택",
            ["Spotify (자동 생성 지원)", "YouTube Music (추후 지원 예정)", "Apple Music (추후 지원 예정)", "Melon / FLO (추후 지원 예정)"]
        )
        
    with col2:
        # 분위기 슬라이더 및 세부 키워드 입력
        mood_energy = st.slider("음악 에너지/강도 (1: 잔잔함 ~ 10: 강렬함)", min_value=1, max_value=10, value=5)
        mood_text = st.text_input("세부 분위기 키워드", placeholder="예: 몽환적인, 쓸쓸한, 포근한, 신나는")
        count = st.slider("추천 곡 수", min_value=3, max_value=15, value=5)

    # 상황 설명 입력창
    situation = st.text_area(
        "청취 상황 및 장소 설명",
        placeholder="예: 비 오는 날 새벽, 창밖을 보며 혼자 따뜻한 아메리카노를 마실 때"
    )
    
    # 1차 생성 버튼
    submit_button = st.form_submit_button("✨ 플레이리스트 추천받기", use_container_width=True)

# 4. Gemini API 추천 호출 흐름 (요청사항 2 반영)
if submit_button:
    if not situation.strip() or not mood_text.strip():
        st.warning("⚠️ 분위기 키워드와 청취 상황을 모두 입력해 주세요!")
    else:
        combined_mood = f"{mood_text} (에너지 레벨: {mood_energy}/10)"
        with st.spinner("🤖 Gemini AI가 맞춤형 곡들을 큐레이팅하는 중입니다..."):
            try:
                result = recommend_playlist(genre, combined_mood, situation, count)
                st.session_state.recommendation = result
                st.session_state.playlist_url = None  # 이전 연동 결과 초기화
                st.success("🎉 AI 추천 플레이리스트 작성이 완료되었습니다!")
            except Exception as e:
                st.error(f"❌ Gemini API 연동 오류 발생: {e}")

# 5. 추천 결과 카드/레이아웃 출력 (요청사항 3 반영)
if st.session_state.recommendation:
    rec = st.session_state.recommendation
    
    st.divider()
    st.subheader(f"🎶 {rec.get('playlist_title', 'AI 맞춤 플레이리스트')}")
    st.info(f"💡 **AI DJ 큐레이션 노트:** {rec.get('description', '')}")
    
    st.markdown("### 📋 추천 트랙 목록")
    
    tracks = rec.get("tracks", [])
    for idx, track in enumerate(tracks, 1):
        with st.container():
            c1, c2 = st.columns([1, 5])
            with c1:
                st.metric(label="Track", value=f"#{idx}")
            with c2:
                st.markdown(f"### **{track['title']}**")
                st.markdown(f"🎤 **아티스트:** {track['artist']}")
                st.caption(f"📝 **추천 이유:** {track['reason']}")
            st.divider()

    # 6. 플랫폼 연동 및 저장 흐름 (요청사항 2 반영)
    st.subheader("2. 🟢 사용 중인 앱으로 플레이리스트 내보내기")
    
    if "Spotify" in platform:
        if st.button("🟢 Spotify 내 계정에 플레이리스트 저장하기", type="primary", use_container_width=True):
            with st.spinner("🎧 Spotify 곡 검색 및 계정 연동 진행 중..."):
                try:
                    sp = get_spotify_client(sp_oauth)
                    track_uris, missing_tracks = get_track_uris(sp, tracks) if sp else ([], [])

                    if sp is None:
                        st.warning("⚠️ 먼저 페이지 상단에서 Spotify 계정을 연결해 주세요.")
                    elif not track_uris:
                        st.error("❌ Spotify에서 일치하는 트랙을 찾을 수 없습니다.")
                    else:
                        url = create_spotify_playlist(
                            sp,
                            rec.get("playlist_title", "AI 추천 플레이리스트"),
                            track_uris,
                            rec.get("description", "")
                        )
                        st.session_state.playlist_url = url
                        if not url:
                            st.error("❌ 플레이리스트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.")

                        if missing_tracks:
                            st.warning(f"⚠️ 다음 곡은 Spotify 검색 결과가 없어 제외되었습니다: {', '.join(missing_tracks)}")
                except Exception as e:
                    st.error(f"❌ Spotify 연동 실패: {e}")
    else:
        st.info(f"현재 선택하신 '{platform}' 서비스는 연동 준비 중입니다. 먼저 Spotify 연동을 테스트해 보세요!")

# 7. 플레이리스트 생성 성공 링크 안내
if st.session_state.playlist_url:
    st.balloons()
    st.success("🎉 성공적으로 사용자 계정에 플레이리스트가 생성되었습니다!")
    st.link_button("🚀 Spotify 앱/웹에서 생성된 플레이리스트 바로 열기", st.session_state.playlist_url, use_container_width=True)