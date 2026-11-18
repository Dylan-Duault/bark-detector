"""Persistence models. HTTP validation models live in app.schemas."""
from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Day(Base):
    __tablename__ = 'days'
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    has_log: Mapped[bool] = mapped_column(Boolean, default=False)


class Detection(Base):
    __tablename__ = 'detections'
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    hour: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[str] = mapped_column(String(26))
    volume: Mapped[float] = mapped_column(Float, default=0)
    legacy_key: Mapped[str | None] = mapped_column(String, unique=True)


class BarkSession(Base):
    __tablename__ = 'bark_sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    started_at: Mapped[str] = mapped_column(String(26))
    ended_at: Mapped[str] = mapped_column(String(26))
    seconds: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer)
    legacy_key: Mapped[str | None] = mapped_column(String, unique=True)


class MusicEvent(Base):
    __tablename__ = 'music_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    time: Mapped[str] = mapped_column(String(8))
    track: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str] = mapped_column(Text, default='')
    legacy_key: Mapped[str | None] = mapped_column(String, unique=True)


class LiveVoiceEvent(Base):
    __tablename__ = 'live_voice_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    time: Mapped[str] = mapped_column(String(8))


class Recording(Base):
    __tablename__ = 'recordings'
    name: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    time: Mapped[str] = mapped_column(String(8))
    duration: Mapped[float] = mapped_column(Float)
    size: Mapped[int] = mapped_column(Integer)
    modified: Mapped[int] = mapped_column(Integer)


class DetectorState(Base):
    __tablename__ = 'detector'
    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[float] = mapped_column(Float)
    last_audio_at: Mapped[float | None] = mapped_column(Float)
    tracking_since: Mapped[float] = mapped_column(Float)


class Coverage(Base):
    __tablename__ = 'coverage'
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    hour: Mapped[int] = mapped_column(Integer, primary_key=True)
    seconds: Mapped[float] = mapped_column(Float, default=0)


class LegacyImport(Base):
    __tablename__ = 'legacy_imports'
    path: Mapped[str] = mapped_column(String, primary_key=True)
    signature: Mapped[str] = mapped_column(String)
