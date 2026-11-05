import os
import time
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# .env 파일 로드
load_dotenv()

# 프로젝트 내 모듈 불러오기
from services.gemini_service import recommend_playlist

# ---------------------------------------------------------
# 1. 테스트 시나리오 데이터셋 (다양한 장르/상황 5가지)
# ---------------------------------------------------------
TEST_SCENARIOS = [
    {"genre": "K-Pop/R&B", "mood": "몽환적이고 차분한", "situation": "비 오는 날 새벽 카페", "count": 5},
    {"genre": "Hip-Hop/Trap", "mood": "에너지 넘치고 신나는", "situation": "헬스장 고강도 운동", "count": 5},
    {"genre": "Indie/Acoustic", "mood": "포근하고 따뜻한", "situation": "주말 오후 집에서 독서", "count": 5},
    {"genre": "Lo-Fi/Chill", "mood": "집중하기 좋은", "situation": "심야 코딩 및 작업", "count": 5},
    {"genre": "Jazz/Classic", "mood": "고급스럽고 클래식한", "situation": "와인 파티 배경음악", "count": 5},
]

def run_advanced_benchmark():
    print("=" * 70)
    print("🚀 [Advanced Portfolio Benchmark] AI 성능, 품질 & Spotify 매칭 정밀 측정")
    print("=" * 70)

    # Spotify 클라이언트 생성
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    
    auth_manager = SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # 누적 수치 저장용 변수
    total_scenarios = len(TEST_SCENARIOS)
    gemini_success_count = 0
    schema_valid_count = 0
    track_count_exact_matches = 0
    
    total_tracks_requested = 0
    exact_matched_count = 0
    fallback_matched_count = 0
    failed_matched_count = 0

    # 품질 및 다양성 지표 변수
    total_unique_tracks = 0
    total_unique_artists = 0

    # Latency 측정 변수
    gemini_latencies = []
    spotify_latencies = []
    total_latencies = []

    # ---------------------------------------------------------
    # 2. 시나리오별 정밀 테스트 루프 실행
    # ---------------------------------------------------------
    for idx, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"\n[Test {idx}/{total_scenarios}] 조건: {scenario['genre']} | {scenario['mood']} | {scenario['situation']}")
        
        start_total = time.time()

        # (1) Gemini API 호출 및 스키마/곡 수 정확도 검증
        start_gemini = time.time()
        try:
            res_data = recommend_playlist(
                genre=scenario["genre"],
                mood=scenario["mood"],
                situation=scenario["situation"],
                count=scenario["count"]
            )
            gemini_latency = time.time() - start_gemini
            gemini_latencies.append(gemini_latency)
            gemini_success_count += 1

            tracks = res_data.get("tracks", [])

            # 스키마 검증
            if "playlist_title" in res_data and "tracks" in res_data:
                schema_valid_count += 1
            
            # 요청 곡 수 일치 여부 검증
            if len(tracks) == scenario["count"]:
                track_count_exact_matches += 1

        except Exception as e:
            print(f"  ❌ Gemini API 호출 실패: {e}")
            continue

        # (2) 추천 품질 검증 (중복 곡 & 아티스트 다양성)
        total_tracks_requested += len(tracks)
        
        # 중복 트랙 및 독자적 아티스트 수 측정
        track_titles = [f"{t.get('title', '').strip().lower()} - {t.get('artist', '').strip().lower()}" for t in tracks]
        artists = [t.get('artist', '').strip().lower() for t in tracks]
        
        unique_tracks_in_res = len(set(track_titles))
        unique_artists_in_res = len(set(artists))
        
        total_unique_tracks += unique_tracks_in_res
        total_unique_artists += unique_artists_in_res

        # (3) Spotify 트랙 검색 & Fallback 매칭 수치 측정
        start_spotify = time.time()
        
        for track in tracks:
            title = track.get("title", "")
            artist = track.get("artist", "")
            
            # 1차 검색: 곡명 + 아티스트
            query_exact = f"track:{title} artist:{artist}"
            exact_res = sp.search(q=query_exact, type="track", limit=1).get("tracks", {}).get("items", [])
            
            if exact_res:
                exact_matched_count += 1
            else:
                # 2차 검색: 곡명 단독 (Fallback)
                fallback_res = sp.search(q=title, type="track", limit=1).get("tracks", {}).get("items", [])
                if fallback_res:
                    fallback_matched_count += 1
                else:
                    failed_matched_count += 1

        spotify_latency = time.time() - start_spotify
        spotify_latencies.append(spotify_latency)

        total_latency = time.time() - start_total
        total_latencies.append(total_latency)

        print(f"  └ ✅ 완료 (Gemini: {gemini_latency:.2f}초 | Spotify: {spotify_latency:.2f}초 | 총: {total_latency:.2f}초)")
        print(f"  └ 🎵 트랙 중복성: {len(tracks) - unique_tracks_in_res}개 중복 | 아티스트 다양성: {unique_artists_in_res}/{len(tracks)}명")

    # ---------------------------------------------------------
    # 3. 종합 수치 집계 및 리포트 출력
    # ---------------------------------------------------------
    total_matched_tracks = exact_matched_count + fallback_matched_count
    
    gemini_success_rate = (gemini_success_count / total_scenarios) * 100
    schema_compliance_rate = (schema_valid_count / gemini_success_count * 100) if gemini_success_count > 0 else 0
    count_accuracy_rate = (track_count_exact_matches / gemini_success_count * 100) if gemini_success_count > 0 else 0

    track_uniqueness_rate = (total_unique_tracks / total_tracks_requested * 100) if total_tracks_requested > 0 else 0
    artist_diversity_rate = (total_unique_artists / total_tracks_requested * 100) if total_tracks_requested > 0 else 0

    track_match_rate = (total_matched_tracks / total_tracks_requested * 100) if total_tracks_requested > 0 else 0
    exact_match_rate = (exact_matched_count / total_tracks_requested * 100) if total_tracks_requested > 0 else 0
    fallback_match_rate = (fallback_matched_count / total_tracks_requested * 100) if total_tracks_requested > 0 else 0

    avg_gemini_latency = sum(gemini_latencies) / len(gemini_latencies) if gemini_latencies else 0
    avg_spotify_latency = sum(spotify_latencies) / len(spotify_latencies) if spotify_latencies else 0
    avg_total_latency = sum(total_latencies) / len(total_latencies) if total_latencies else 0

    print("\n" + "=" * 70)
    print("📊 [포트폴리오 제출용 고도화 최종 수치화 결과 리포트]")
    print("=" * 70)
    print(f"1. LLM 호출 및 규격 무결성")
    print(f"  - AI 플레이리스트 생성 성공률: {gemini_success_rate:.1f}% ({gemini_success_count}/{total_scenarios}회)")
    print(f"  - JSON Structured Output 규격 준수율: {schema_compliance_rate:.1f}% ({schema_valid_count}/{gemini_success_count}회)")
    print(f"  - 요청 곡 수 일치율: {count_accuracy_rate:.1f}% ({track_count_exact_matches}/{gemini_success_count}회)")
    
    print(f"\n2. 추천 데이터 품질 및 다양성 (Playlist Quality)")
    print(f"  - 트랙 고유성(중복 방지율): {track_uniqueness_rate:.1f}% ({total_unique_tracks}/{total_tracks_requested}곡 고유)")
    print(f"  - 아티스트 다양성 비율: {artist_diversity_rate:.1f}% ({total_unique_artists}/{total_tracks_requested}명 고유)")

    print(f"\n3. 음원 검색 및 Fallback 알고리즘 성과")
    print(f"  - 총 추천 요청 트랙 수: {total_tracks_requested}곡")
    print(f"  - 🎯 최종 음원 매칭 성공률: {track_match_rate:.1f}% ({total_matched_tracks}/{total_tracks_requested}곡)")
    print(f"    ├ 1차 정밀 검색 성공률 (곡명+가수): {exact_match_rate:.1f}% ({exact_matched_count}곡)")
    print(f"    └ 2차 Fallback 검색 성공률 (곡명 단독): {fallback_match_rate:.1f}% ({fallback_matched_count}곡)")
    print(f"  - 검색 실패(미존재) 트랙 수: {failed_matched_count}곡")

    print(f"\n4. 시스템 응답 속도 (Latency)")
    print(f"  - 평균 Gemini AI 추천 소요 시간: {avg_gemini_latency:.2f}초")
    print(f"  - 평균 Spotify 음원 매칭 소요 시간: {avg_spotify_latency:.2f}초")
    print(f"  - ⚡ 엔드투엔드 평균 처리 속도: {avg_total_latency:.2f}초 (5곡 기준)")
    print("=" * 70)

if __name__ == "__main__":
    run_advanced_benchmark()