"""One configuration contract shared by the web and detector processes."""
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# systemd sets WorkingDirectory; installed CLI commands use the current project.
ROOT = Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')

    data_dir: Path = ROOT / 'data'
    dashboard_pin: SecretStr = Field(default=SecretStr(''), repr=False)
    cookie_secure: bool = False
    host: str = '0.0.0.0'
    port: int = Field(default=8080, ge=1, le=65535)
    bark_music_enabled: bool = False
    bark_music_bark_count: int = Field(default=20, gt=0)
    bark_music_window_seconds: int = Field(default=300, gt=0)
    bark_music_volume_percent: int = Field(default=35, ge=0, le=100)
    bark_speaker_address: str = '74:68:59:AA:5E:05'
    sample_rate: int = Field(default=16000, ge=16000, le=16000)
    chunk_duration: float = Field(default=1.2, gt=0)
    top_n_classes: int = Field(default=5, ge=1, le=521)
    bark_class_name: str = 'Dog'
    min_bark_volume: float = Field(default=.012, ge=0, le=1)
    consecutive_barks: int = Field(default=2, ge=1)
    record_duration: float = Field(default=60, ge=0)
    record_quiet_seconds: float = Field(default=10, gt=0)
    session_gap_seconds: float = Field(default=90, gt=0)
    min_barks_per_session: int = Field(default=2, ge=1)
    min_session_duration: float = Field(default=0, ge=0)

    @field_validator('data_dir')
    @classmethod
    def absolute_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def require_pin(self) -> str:
        import re
        pin = self.dashboard_pin.get_secret_value()
        if not re.fullmatch(r'[0-9]{4}', pin):
            raise ValueError('DASHBOARD_PIN must contain exactly four digits')
        return pin

    @property
    def music_options(self) -> dict:
        return dict(enabled=self.bark_music_enabled, path=self.data_dir / 'music',
                    bark_count=self.bark_music_bark_count,
                    window_seconds=self.bark_music_window_seconds,
                    volume_percent=self.bark_music_volume_percent,
                    speaker_address=self.bark_speaker_address, data_dir=self.data_dir)
