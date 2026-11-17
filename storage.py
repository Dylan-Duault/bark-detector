"""Shared locations for runtime data, separate from application source."""
from app.config import ROOT as PROJECT_ROOT, Settings
from app.infrastructure.paths import prepare_data_directory

DATA_DIR = Settings().data_dir
LOGS_DIR = DATA_DIR / 'logs'
RECORDINGS_DIR = DATA_DIR / 'recordings'
