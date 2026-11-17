"""Prepare runtime directories without creating sample or measurement data."""
from pathlib import Path
from app.config import Settings


def prepare_data_directory(directory=None):
    directory = Path(directory) if directory is not None else Settings().data_dir
    for name in ('logs', 'recordings'):
        (directory / name).mkdir(parents=True, exist_ok=True)
