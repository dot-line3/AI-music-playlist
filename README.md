# 🎵 AI 맞춤형 음악 플레이리스트 추천 & 자동 생성기

Gemini AI를 활용해 사용자의 장르, 분위기, 청취 상황을 분석하여 맞춤형 플레이리스트를 큐레이팅하고, Spotify OAuth2 API를 통해 본인 계정에 즉시 플레이리스트를 생성해 주는 웹 애플리케이션입니다.

## 🛠 Tech Stack
- **UI:** Streamlit
- **AI Model:** Gemini API (`google-genai` SDK with Fallback Model Chain)
- **Music API:** Spotify API (`spotipy`)
- **Data Validation:** Pydantic

## 🚀 Quick Start

1. **가상환경 생성 및 패키지 설치**
```bash
python -m venv playlistvenv
source playlistvenv/bin/activate  # Windows: playlistvenv\Scripts\activate
pip install -r requirements.txt
```

**환경변수(.env) 설정**
GEMINI_API_KEY=your_gemini_api_key
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8501   # 배포 시: Streamlit 앱 URL

**앱 실행**
streamlit run app.py

## 🔐 Spotify 사용자 인증 구조
- OAuth Authorization Code Flow: 사용자가 "Spotify 계정 연결하기"를 누르면 Spotify 로그인 후 `SPOTIPY_REDIRECT_URI`(이 앱 주소)로 돌아오고, 앱이 `code`를 토큰으로 교환합니다.
- 토큰은 서버 공용 파일(`.cache`)이 아닌 **각 사용자의 Streamlit 세션(`st.session_state`)에만 저장**되어, 동시 접속 시에도 다른 사용자 계정에 플레이리스트가 생성되지 않습니다.
- 일회성 `state` 값으로 CSRF를 방지합니다.
- Spotify Developer Dashboard의 Redirect URIs에 `SPOTIPY_REDIRECT_URI`와 같은 주소를 등록해야 합니다.

## 🎯 트랙 매칭 로직
1. `track:{곡명} artist:{가수}` 정밀 검색 (Spotify 아티스트 필터 적용, 표기가 같은 곡 우선)
2. 실패 시 곡명 단독 검색 (상위 10건 중 아티스트 일치 곡)
3. 아티스트가 일치하는 곡이 없으면 제외 → 동명이곡 오매칭 및 AI 환각 곡을 걸러냄

## ⚡ 모델 우회 체인
`gemini-3.5-flash-lite → gemini-3.1-flash-lite → gemini-2.5-flash`
- 503/429 오류 시 1초 후 1회 재시도, 실패하면 다음 모델로 전환
- 응답 지연 기반 전환: 앞의 두 모델은 10초 안에 응답이 없으면 다음 모델로 넘어감

## 📊 벤치마크 결과 (2026-11-09 측정)

`test_metrics.py` (5개 장르·상황 × 5곡 = 25곡)

| 지표 | 결과 |
|---|---|
| Gemini 추천 응답 | 평균 **2.18초** (최소 1.87 ~ 최대 2.45초), 엔드투엔드 3.68초 |
| JSON 규격 준수 / 요청 곡 수 일치 | 100% / 100% |
| 음원 매칭률 | **84%** (21/25곡), 다른 가수 곡 오매칭 0건 |
| 매칭 실패 처리 | Spotify에서 찾을 수 없는 4곡은 플레이리스트에서 제외하고 화면에 안내 |

`test_concurrent.py` (5명 동시 요청): 전원 성공, 평균 3.48초 / 최대 4.28초

### 속도와 정확도의 트레이드오프
같은 테스트로 1순위 모델을 비교한 결과입니다.

| 1순위 모델 | Gemini 평균 응답 | 응답 범위 | 매칭률 |
|---|---|---|---|
| gemini-3.1-flash-lite | 11.49초 | 2.0 ~ 20.9초 | 100% |
| gemini-3.5-flash-lite (현재) | 2.18초 | 1.9 ~ 2.5초 | 84% |

체감 속도를 우선하고, 없는 곡은 아티스트 검증으로 걸러내는 쪽을 선택했습니다.

## 🧪 테스트 실행
```bash
python test_metrics.py      # 품질·매칭률·지연 측정
python test_concurrent.py   # 5명 동시 요청 부하 테스트
```
