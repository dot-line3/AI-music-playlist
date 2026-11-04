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
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

**앱 실행**
streamlit run app.py
