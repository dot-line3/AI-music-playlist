import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from services.gemini_service import recommend_playlist
from services.spotify_service import match_track

load_dotenv()

# 5명의 가상 유저 조건 시나리오 (동시 접속)
VIRTUAL_USERS = [
    {"user_id": "User_1 (K-Pop)", "genre": "K-Pop", "mood": "신나는", "situation": "드라이브", "count": 5},
    {"user_id": "User_2 (HipHop)", "genre": "Hip-Hop", "mood": "강렬한", "situation": "고강도 운동", "count": 5},
    {"user_id": "User_3 (LoFi)", "genre": "Lo-Fi", "mood": "차분한", "situation": "심야 코딩", "count": 5},
    {"user_id": "User_4 (Jazz)", "genre": "Jazz", "mood": "고급스러운", "situation": "와인 파티", "count": 5},
    {"user_id": "User_5 (Indie)", "genre": "Indie", "mood": "따뜻한", "situation": "독서", "count": 5},
]

def simulate_user_request(user_info: dict) -> dict:
    """단일 가상 유저의 처리 단위 (Gemini 추천 + Spotify 검색)"""
    user_id = user_info["user_id"]
    start_time = time.time()
    
    # 스레드별 독립된 Spotify 검색 클라이언트 생성
    # (참고: 이 테스트는 동시 요청 처리량을 측정하며, 사용자 계정 토큰 격리는 app.py의 SessionCacheHandler가 담당)
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET")
    ))
    
    try:
        # 1. Gemini AI 추천 요청
        gemini_start = time.time()
        res_data = recommend_playlist(
            genre=user_info["genre"],
            mood=user_info["mood"],
            situation=user_info["situation"],
            count=user_info["count"]
        )
        gemini_latency = time.time() - gemini_start

        tracks = res_data.get("tracks", [])
        
        # 2. Spotify 검색 실행 (1차 정밀 ➔ 2차 Fallback)
        spotify_start = time.time()
        matched_count = 0
        for t in tracks:
            uri, _ = match_track(sp, t.get("title", ""), t.get("artist", ""))
            if uri:
                matched_count += 1
        spotify_latency = time.time() - spotify_start

        total_latency = time.time() - start_time

        return {
            "user_id": user_id,
            "success": True,
            "gemini_latency": gemini_latency,
            "spotify_latency": spotify_latency,
            "total_latency": total_latency,
            "track_count": len(tracks),
            "matched_count": matched_count,
            "playlist_title": res_data.get("playlist_title", "")
        }

    except Exception as e:
        return {
            "user_id": user_id,
            "success": False,
            "error": str(e),
            "total_latency": time.time() - start_time
        }

def run_concurrent_test(num_workers: int = 5):
    print("=" * 70)
    print(f"🔥 [Multi-User Load Test] {num_workers}명 동시 접속 시뮬레이션 시작")
    print("=" * 70)

    start_all = time.time()
    results = []

    # ThreadPoolExecutor로 num_workers개의 동시 스레드 즉시 발사
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(simulate_user_request, user) for user in VIRTUAL_USERS[:num_workers]]
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            if res["success"]:
                print(f"  └ 🏁 [{res['user_id']}] 성공 (소요: {res['total_latency']:.2f}초 | 제목: {res['playlist_title']})")
            else:
                print(f"  └ ❌ [{res['user_id']}] 실패: {res['error']}")

    total_elapsed = time.time() - start_all

    # 통계 수치 계산
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    
    latencies = [r["total_latency"] for r in successes]
    gemini_latencies = [r["gemini_latency"] for r in successes]

    print("\n" + "=" * 70)
    print("📊 [다중 사용자 동시성 테스트 최종 리포트]")
    print("=" * 70)
    print(f"1. 동시성 처리 가용성")
    print(f"  - 동시 가상 유저 수: {num_workers}명")
    print(f"  - 동시 요청 성공률: {(len(successes)/num_workers)*100:.1f}% ({len(successes)}/{num_workers}명)")
    print(f"  - 전체 동시 처리 완료 소요 시간: {total_elapsed:.2f}초")
    
    if successes:
        print(f"\n2. 동시 접속 Latency 분산 (병목도 측정)")
        print(f"  - 평균 사용자 처리 속도: {sum(latencies)/len(latencies):.2f}초")
        print(f"  - 최속 응답 사용자 (Min): {min(latencies):.2f}초")
        print(f"  - 최장 응답 사용자 (Max): {max(latencies):.2f}초")
        print(f"  - 동시 요청 시 평균 AI 생성 시간: {sum(gemini_latencies)/len(gemini_latencies):.2f}초")

    if failures:
        print(f"\n3. 동시성 실패 원인")
        for f in failures:
            print(f"  - [{f['user_id']}] 오류 내용: {f['error']}")
    print("=" * 70)

if __name__ == "__main__":
    run_concurrent_test(num_workers=5)