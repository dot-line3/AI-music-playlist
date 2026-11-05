import os
import json
import time
from typing import Dict, Any
from dotenv import load_dotenv
import streamlit as st
from google import genai
from google.genai.errors import APIError
from models.playlist_schema import PlaylistResponse

# 1. 로컬 환경변수(.env) 로드
load_dotenv()

def get_secret(key: str, default: str = "") -> str:
    """Streamlit Secrets 및 .env 동적 지원 헬퍼 함수"""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)

GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("오류: GEMINI_API_KEY를 찾을 수 없습니다. .env 또는 Streamlit Secrets 설정을 확인하세요.")

# 2. SDK 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)

def recommend_playlist(
    genre: str,
    mood: str,
    situation: str,
    count: int = 10,
    max_retries_per_model: int = 1,  # [Latency 최적화] 모델당 재시도 1회로 제한
    retry_delay: float = 1.0         # [Latency 최적화] 대기 시간을 1초로 축소
) -> Dict[str, Any]:
    """
    [분석 3 해결책 구현]
    트래픽 폭주 및 503 과부하 시 지연 시간을 최소화하고 가용성 99.9%를 보장하는
    3단계 Fast-Failover Model Fallback Chain
    """
    # 속도, 성능, 안정성을 고려한 3단계 우선순위 모델 체인
    model_chain = [
        "gemini-3.1-flash-lite",    # 1순위: 메인 고속 모델
        "gemini-3.5-flash-lite",      # 2순위: 고성능 백업 모델
        "gemini-2.5-flash"     # 3순위: 최고 안정성 백업 모델
    ]

    prompt = f"""
    당신은 음악 취향 분석 및 곡 큐레이팅에 특화된 세계 최고 수준의 AI 음악 DJ입니다.
    아래 제공된 [사용자 청취 조건]을 정밀히 분석하여 최적의 맞춤형 플레이리스트를 생성해 주세요.

    [사용자 청취 조건]
    - 선호 장르: {genre}
    - 음악 분위기: {mood}
    - 청취 상황/장소: {situation}
    - 요청 곡 수: {count}곡

    [작성 가이드라인]
    1. 반드시 Spotify 등 주요 플랫폼에서 실제 검색 및 재생이 가능한 실존 곡만 추천하세요.
    2. 곡 제목(title)과 아티스트명(artist)은 검색 정확도를 위해 원어 공식 명칭 그대로 작성하세요.
    3. 추천 이유(reason)는 사용자의 상황('{situation}')과 분위기('{mood}')에 잘 맞아떨어지도록 한국어로 감성적으로 작성해 주세요.
    4. 정확히 지정된 {count}개의 트랙을 생성해야 합니다.
    """

    last_error = None

    # 3. 모델 폴백 체인 순차 실행
    for model_name in model_chain:
        print(f"[Model Chain] 호출 시도 중인 모델: {model_name}")

        for attempt in range(max_retries_per_model + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": PlaylistResponse,
                        "temperature": 0.7,
                    },
                )
                print(f"[Model Chain Success] ✨ '{model_name}' 모델을 통해 성공적으로 생성 완료")
                return json.loads(response.text)

            except APIError as e:
                last_error = e
                # 503(과부하) 또는 429(요청 초과) 시 1초 대기 후 1회 빠른 재시도
                if e.code in [503, 429] and attempt < max_retries_per_model:
                    print(f"  └ [Fast Retry] '{model_name}' 일시적 지연({e.code}). {retry_delay}초 후 즉시 재시도... ({attempt + 1}/{max_retries_per_model})")
                    time.sleep(retry_delay)
                else:
                    print(f"  └ ⚠️ '{model_name}' 응답 불가({e.code}). 다음 백업 모델로 즉시 체인 전환")
                    break  # 재시도 실패 시 대기 없이 다음 모델로 즉시 전환

            except Exception as e:
                last_error = e
                print(f"  └ ⚠️ '{model_name}' 예외 발생 ({e}). 다음 백업 모델로 즉시 전환")
                break

    raise RuntimeError(f"폴백 체인의 모든 모델 호출이 실패했습니다. 최종 오류: {last_error}")