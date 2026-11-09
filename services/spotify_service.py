import os
import re
import secrets
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()


def get_config(key: str, default: str = "") -> str:
    """Streamlit Cloud Secrets 우선, 없으면 로컬 .env/환경변수 사용"""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()


SCOPE = "playlist-modify-public playlist-modify-private"
ARTIST_MATCH_THRESHOLD = 0.9  # 아티스트명 유사도 기준 (0~1). 0.8은 "Chet Baker"/"Chet Faker"를 같은 가수로 판정


# ---------------------------------------------------------------------------
# 1. 사용자별 토큰 격리: Streamlit 세션 단위 캐시 핸들러
# ---------------------------------------------------------------------------
class SessionCacheHandler(CacheHandler):
    """
    OAuth 토큰을 서버 공용 파일(.cache)이 아니라 각 사용자의 세션 저장소(st.session_state)에 보관.
    -> 여러 사용자가 동시에 접속해도 A의 토큰으로 B의 플레이리스트가 생성되지 않음.
    """

    def __init__(self, session_store, key: str = "spotify_token_info"):
        self.store = session_store
        self.key = key

    def get_cached_token(self):
        return self.store.get(self.key)

    def save_token_to_cache(self, token_info):
        self.store[self.key] = token_info

    def clear(self):
        if self.key in self.store:
            del self.store[self.key]


def create_oauth_manager(cache_handler: CacheHandler) -> SpotifyOAuth:
    """세션 전용 캐시를 사용하는 OAuth 매니저 생성 (서버에서 브라우저를 열지 않음)"""
    return SpotifyOAuth(
        client_id=get_config("SPOTIPY_CLIENT_ID"),
        client_secret=get_config("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=get_config("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8501"),
        scope=SCOPE,
        cache_handler=cache_handler,
        open_browser=False,
        show_dialog=True,
    )


def new_oauth_state() -> str:
    """CSRF 방지용 일회성 state 값"""
    return secrets.token_urlsafe(16)


def get_spotify_client(oauth: SpotifyOAuth) -> Optional[spotipy.Spotify]:
    """현재 세션에 유효한 토큰이 있을 때만 클라이언트 반환 (만료 시 refresh_token으로 자동 갱신)"""
    if not oauth.validate_token(oauth.cache_handler.get_cached_token()):
        return None
    return spotipy.Spotify(auth_manager=oauth, requests_timeout=10)


# ---------------------------------------------------------------------------
# 2. 트랙 매칭: 1차 정밀 검색 -> 2차 곡명 검색 + 아티스트 검증
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """대소문자/악센트/공백/특수문자 차이를 제거한 비교용 문자열"""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[\W_]+", "", text.lower())


def _artist_aliases(artist: str) -> list[str]:
    """'아이유 (IU)', 'A & B', 'A feat. B' 같은 표기를 개별 이름으로 분리"""
    parts = re.split(r"\(|\)|,|&|/|\bfeat\.?|\bft\.?", artist, flags=re.IGNORECASE)
    return [n for n in (_normalize(p) for p in parts + [artist]) if n]


def artist_matches(requested_artist: str, track_artists: list[str]) -> bool:
    """추천된 아티스트와 검색 결과 아티스트가 같은 사람인지 판정"""
    wanted = _artist_aliases(requested_artist)
    found = [_normalize(a) for a in track_artists if _normalize(a)]
    for w in wanted:
        for f in found:
            if w == f:
                return True
            if min(len(w), len(f)) >= 3 and (w in f or f in w):
                return True
            if SequenceMatcher(None, w, f).ratio() >= ARTIST_MATCH_THRESHOLD:
                return True
    return False


def _clean_query_text(text: str) -> str:
    return text.replace('"', "").replace("'", "").strip()


def match_track(sp, title: str, artist: str) -> tuple[Optional[str], str]:
    """
    추천 곡 1개를 Spotify 트랙 URI로 변환.
    반환: (uri 또는 None, 매칭 유형)
      - "exact": 곡명+아티스트 필드 검색 결과 (Spotify의 artist: 필터가 '아이유'/'IU' 같은 별칭까지 처리)
      - "fallback": 곡명 단독 검색 결과 중 아티스트가 일치하는 곡
      - "not_found": 아티스트가 일치하는 곡 없음 (다른 가수의 동명 곡은 매칭하지 않음)
    """
    t, a = _clean_query_text(title), _clean_query_text(artist)

    exact_items = sp.search(q=f"track:{t} artist:{a}", type="track", limit=5).get("tracks", {}).get("items", [])
    if exact_items:
        # 표기가 정확히 같은 아티스트를 우선 선택, 없으면 Spotify 필터 결과 1순위 사용
        for item in exact_items:
            if artist_matches(artist, [x["name"] for x in item.get("artists", [])]):
                return item["uri"], "exact"
        return exact_items[0]["uri"], "exact"

    # 2차 곡명 단독 검색은 아티스트 필터가 없으므로 반드시 아티스트 일치 여부를 검증

    fallback_items = sp.search(q=t, type="track", limit=10).get("tracks", {}).get("items", [])
    for item in fallback_items:
        if artist_matches(artist, [x["name"] for x in item.get("artists", [])]):
            return item["uri"], "fallback"

    return None, "not_found"


def get_track_uris(sp, recommended_tracks):
    """추천 곡 목록을 Spotify에서 검색하고 실시간 진행 로그를 출력합니다."""
    track_uris = []
    not_found_tracks = []

    print(f"\n[Spotify Track Search] 총 {len(recommended_tracks)}곡 검색 시작...")

    for idx, track in enumerate(recommended_tracks, 1):
        title = track.get("title", "")
        artist = track.get("artist", "")
        try:
            print(f" └ [{idx}/{len(recommended_tracks)}] 검색 중: {title} - {artist}")
            uri, match_type = match_track(sp, title, artist)
            if uri:
                track_uris.append(uri)
                print(f"     ➔ Found ({match_type}): {uri}")
            else:
                not_found_tracks.append(f"{title} - {artist}")
                print("     ❌ Not Found (아티스트 일치 곡 없음)")
        except Exception as e:
            print(f"     ⚠️ [{title}] 검색 중 에러 발생: {e}")
            not_found_tracks.append(f"{title} - {artist}")

    return track_uris, not_found_tracks


def create_spotify_playlist(sp, playlist_name, track_uris, description="AI 추천 맞춤형 플레이리스트"):
    """현재 인증된 사용자 계정에 플레이리스트를 생성하고 트랙들을 추가합니다."""
    try:
        print("\n[Spotify Playlist] 플레이리스트 생성 중 (/v1/me/playlists)...")
        playlist = sp.current_user_playlist_create(
            name=playlist_name,
            public=True,
            description=description,
        )

        if track_uris:
            print(f"[Spotify Playlist] 트랙 {len(track_uris)}개 추가 중...")
            sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

        return playlist["external_urls"]["spotify"]
    except Exception as e:
        print(f"[Error] 플레이리스트 생성 처리 중 오류: {e}")
        return None
