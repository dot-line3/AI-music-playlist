from services.gemini_service import recommend_playlist
from services.spotify_service import get_spotify_client, get_track_uris, create_spotify_playlist

if __name__ == "__main__":
    # 1. 테스트 조건 입력
    genre = "Indie Pop, R&B"
    mood = "몽환적이고 감성적인"
    situation = "비 오는 날 새벽, 창밖을 보며 혼자 커피 마실 때"
    count = 5

    print("1. Gemini API에 플레이리스트 추천 요청 중...\n")
    ai_response = recommend_playlist(genre, mood, situation, count)
    
    playlist_title = ai_response.get("playlist_title", "AI 추천 플레이리스트")
    tracks = ai_response.get("tracks", [])
    
    print(f"=== [추천 플레이리스트] ===")
    print(f"제목: {playlist_title}")
    print(f"설명: {ai_response.get('description')}\n")
    print("--- 추천 곡 목록 ---")
    for idx, track in enumerate(tracks, 1):
        print(f"{idx}. {track['title']} - {track['artist']}")
        print(f"   └ 이유: {track['reason']}")

    print("\n2. Spotify API 인증 및 곡 검색 진행 중...")
    sp = get_spotify_client()
    track_uris, missing_tracks = get_track_uris(sp, tracks)

    print(f"- Spotify Track URI 검색 성공: {len(track_uris)} / {len(tracks)}곡")
    if missing_tracks:
        print(f"- 검색 결과 없음 (예외 처리): {missing_tracks}")

    print("\n3. Spotify 플레이리스트 자동 생성 및 곡 추가 중...")
    playlist_url = create_spotify_playlist(
        sp, 
        playlist_title, 
        track_uris, 
        ai_response.get("description", "AI 추천 맞춤형 플레이리스트")
    )

    if playlist_url:
        print(f"\n🎉 성공적으로 생성되었습니다!")
        print(f"🔗 생성된 플레이리스트 확인: {playlist_url}")
    else:
        print("\n❌ 플레이리스트 생성에 실패했습니다.")