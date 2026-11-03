from pydantic import BaseModel, Field
from typing import List

class TrackItem(BaseModel):
    """개별 트랙 정보 스키마"""
    title: str = Field(description="곡의 정확한 원제목")
    artist: str = Field(description="아티스트 또는 가수 이름")
    reason: str = Field(description="이 곡을 추천하는 감성적/상황적 이유 (한국어 한 문장)")

class PlaylistResponse(BaseModel):
    """전체 플레이리스트 응답 스키마"""
    playlist_title: str = Field(description="추천 플레이리스트 전체 컨셉 제목")
    description: str = Field(description="플레이리스트 종합 설명")
    tracks: List[TrackItem] = Field(description="추천된 트랙 목록")