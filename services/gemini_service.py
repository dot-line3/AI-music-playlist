import os
import json
import time
from typing import Dict, Any
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError
from models.playlist_schema import PlaylistResponse

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("오류: .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")

client = genai.Client(api_key=GEMINI_API_KEY)

# 멀티 모델 체인 순서 정의 (주 모델 -> 고성능 보조 모델 -> 높은 안정성 백업 모델)
MODEL_CHAIN = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash"
]

def recommend_playlist(
    genre: str,
    mood: str,
    situation: str,
    count: int = 10,
    max_retries_per_model: int = 2
) -> Dict[str, Any]:
    """
    여러 Gemini 모델을 체인(Fallback Chain) 구조로 순차 호출합니다.
    특정 모델에서 503(과부하) 또는 429(속도제한) 발생 시 재시도 후, 
    해결되지 않으면 다음 모델로 자동 전환되어 플레이리스트를 생성합니다.
    """
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

    last_exception = None

    for model_name in MODEL_CHAIN:
        print(f"[Model Chain] 호출 시도 중인 모델: {model_name}")
        
        for attempt in range(max_retries_per_model):
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
                print(f"[Model Chain Success] ✨ '{model_name}' 모델을 통해 성공적으로 플레이리스트를 생성했습니다.\n")
                return json.loads(response.text)

            except APIError as e:
                last_exception = e
                # 503 (Unavailable) 또는 429 (Rate Limit) 발생 시 대기 후 재시도
                if e.code in (503, 429):
                    wait_time = (attempt + 1) * 2
                    print(f" └ [Warning] '{model_name}' 트랙 과부하/제한({e.code}). {wait_time}초 후 재시도... ({attempt + 1}/{max_retries_per_model})")
                    time.sleep(wait_time)
                else:
                    print(f" └ [Error] '{model_name}' API 오류 발생: {e}")
                    break  # 다음 모델로 체인 전환

            except Exception as e:
                last_exception = e
                print(f" └ [Error] '{model_name}' 처리 중 예외 발생: {e}")
                break  # 다음 모델로 체인 전환
        
        print(f" └ ⚠️ '{model_name}' 응답 불가. 다음 백업 모델로 체인 전환합니다.\n")

    # 체인 내 모든 모델 호출이 실패한 경우
    raise RuntimeError(f"모든 모델 체인 호출에 실패했습니다. 마지막 오류: {last_exception}")