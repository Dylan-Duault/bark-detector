"""Public HTTP contracts, separate from persistence models."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pin: str = Field(min_length=4, max_length=4, pattern=r'^[0-9]{4}$', repr=False)


class DetectorStatus(BaseModel):
    state: str
    updated_at: float | None
    last_audio_at: float | None
    tracking_since: float | None


class DaySummary(BaseModel):
    date: str
    detections: int
    sessions: int
    seconds: float
    recordings: int
    hours: list[int]
    listened_hours: list[float] | None
    listened_seconds: float | None
    has_data: bool


class TrendDay(DaySummary):
    has_log: bool


class Trends(BaseModel):
    period: Literal[7, 30]
    start: str
    end: str
    days: list[TrendDay]
    hours: list[int]
    listened_seconds: float | None


class RecordingInfo(BaseModel):
    name: str
    date: str
    time: str
    duration: float
    url: str


class MusicInfo(BaseModel):
    date: str
    time: str
    status: Literal['started', 'failed']
    track: str
    detail: str


class LiveVoiceInfo(BaseModel):
    id: int
    date: str
    time: str


class DashboardResponse(BaseModel):
    date: str
    detector: DetectorStatus
    summary: DaySummary
    trends: Trends
    days: list[DaySummary]
    recordings: list[RecordingInfo]
    music_events: list[MusicInfo]
    live_voice_events: list[LiveVoiceInfo]


class WaveformResponse(BaseModel):
    duration: float
    step: float
    levels: list[float]
    peak_dbfs: float
