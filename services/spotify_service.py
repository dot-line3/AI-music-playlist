import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

def get_spotify_client():
    """Spotify OAuth2 인증 클라이언트를 생성합니다."""
    scope = "playlist-modify-public playlist-modify-private"
    
    auth_manager = SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=scope,
        open_browser=True,
        show_dialog=True  # 👈 권한 동의 창을 확실하게 다시 띄우도록 설정
    )
    
    sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=10)
    return sp

def get_track_uris(sp, recommended_tracks):
    """
    추천 곡 목록을 Spotify에서 검색하고 실시간 진행 로그를 출력합니다.
    """
    track_uris = []
    not_found_tracks = []

    print(f"\n[Spotify Track Search] 총 {len(recommended_tracks)}곡 검색 시작...")

    for idx, track in enumerate(recommended_tracks, 1):
        title = track.get('title', '')
        artist = track.get('artist', '')
        query = f"track:{title} artist:{artist}"
        
        try:
            print(f" └ [{idx}/{len(recommended_tracks)}] 검색 중: {title} - {artist}")
            result = sp.search(q=query, type="track", limit=1)
            tracks = result.get("tracks", {}).get("items", [])
            
            if tracks:
                track_uris.append(tracks[0]["uri"])
                print(f"     ➔ Found: {tracks[0]['name']} ({tracks[0]['uri']})")
            else:
                # 1차 정확한 검색 실패 시 곡 제목만으로 2차 재검색
                fallback_result = sp.search(q=title, type="track", limit=1)
                fallback_tracks = fallback_result.get("tracks", {}).get("items", [])
                
                if fallback_tracks:
                    track_uris.append(fallback_tracks[0]["uri"])
                    print(f"     ➔ Found (Title only): {fallback_tracks[0]['name']}")
                else:
                    not_found_tracks.append(f"{title} - {artist}")
                    print(f"     ❌ Not Found")
                    
        except Exception as e:
            print(f"     ⚠️ [{title}] 검색 중 에러 발생: {e}")
            not_found_tracks.append(f"{title} - {artist}")

    return track_uris, not_found_tracks

def create_spotify_playlist(sp, playlist_name, track_uris, description="AI 추천 맞춤형 플레이리스트"):
    """
    현재 인증된 사용자 계정에 플레이리스트를 생성하고 트랙들을 추가합니다.
    """
    try:
        print("\n[Spotify Playlist] 플레이리스트 생성 중 (/v1/me/playlists)...")
        # 👈 user_id 파라미터 대신 current_user_playlist_create 사용
        playlist = sp.current_user_playlist_create(
            name=playlist_name,
            public=True,
            description=description
        )
        
        if track_uris:
            print(f"[Spotify Playlist] 트랙 {len(track_uris)}개 추가 중...")
            sp.playlist_add_items(
                playlist_id=playlist["id"],
                items=track_uris
            )
            
        return playlist["external_urls"]["spotify"]
    except Exception as e:
        print(f"[Error] 플레이리스트 생성 처리 중 오류: {e}")
        return None