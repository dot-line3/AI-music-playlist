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


def _thinking_config(model_name: str) -> dict:
    """
    곡 추천은 깊은 추론이 필요 없는 생성 작업이므로 생각(thinking) 토큰을 최소화해 지연을 줄인다.
    (미설정 시 gemini-3.1-flash-lite 응답이 2~21초로 크게 흔들림, 평균 11.49초 측정)
    모델 세대별로 파라미터가 다름: Gemini 3 = thinking_level, Gemini 2.5 = thinking_budget
    """
    if model_name.startswith("gemini-2."):
        return {"thinking_budget": 0}
    return {"thinking_level": "LOW"}

def recommend_playlist(
    genre: str,
    mood: str,
    situation: str,
    count: int = 10,
    max_retries_per_model: int = 1,  # [Latency 최적화] 모델당 재시도 1회로 제한
    retry_delay: float = 1.0         # [Latency 최적화] 대기 시간을 1초로 축소
) -> Dict[str, Any]:
    """
    트래픽 폭주 및 503/429 과부하 시 모델당 1회만 빠르게 재시도한 뒤
    다음 모델로 전환하는 3단계 Fast-Failover Model Fallback Chain
    """
    # 속도, 성능, 안정성을 고려한 3단계 우선순위 모델 체인
    model_chain = [
        "gemini-3.5-flash-lite",    # 1순위: 메인 고속 모델
        "gemini-3.1-flash-lite",    # 2순위: 백업 모델
        "gemini-3.6-flash"          # 3순위: 최종 백업 모델 (gemini-2.5-flash가 응답 없이 멈춰 교체)
    ]
    # 응답 지연 기반 전환: 정상 응답은 2초 안팎이지만 서버 혼잡 시 40초 이상 걸리는 경우가 측정됨.
    # 앞 모델은 10초 안에 응답이 없으면 끊고 다음 모델로 넘어가며, 마지막 모델만 20초까지 대기한다.
    timeouts_ms = {"gemini-3.5-flash-lite": 10_000, "gemini-3.1-flash-lite": 10_000, "gemini-3.6-flash": 20_000}

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
                        "thinking_config": _thinking_config(model_name),
                        "http_options": {"timeout": timeouts_ms.get(model_name, 20_000)},
                    },
                )
                print(f"[Model Chain Success] ✨ '{model_name}' 모델을 통해 성공적으로 생성 완료")
                result = json.loads(response.text)
                result["_model_used"] = model_name  # 측정/로그용 (UI에서는 사용하지 않음)
                return result

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
                # 타임아웃(응답 지연)도 여기서 처리되어 다음 모델로 전환됨
                print(f"  └ ⚠️ '{model_name}' {type(e).__name__} ({e}). 다음 백업 모델로 즉시 전환")
                break

    raise RuntimeError(f"폴백 체인의 모든 모델 호출이 실패했습니다. 최종 오류: {last_error}")