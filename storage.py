"""Shared locations for runtime data, separate from application source."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / 'data'
LOGS_DIR = DATA_DIR / 'logs'
RECORDINGS_DIR = DATA_DIR / 'recordings'


def prepare_data_directory(directory=DATA_DIR):
    directory = Path(directory)
    (directory / 'logs').mkdir(parents=True, exist_ok=True)
    (directory / 'recordings').mkdir(parents=True, exist_ok=True)
