"""Recording metadata indexing and bounded waveform analysis."""
from array import array
from functools import lru_cache
import datetime as dt
import math
from pathlib import Path
import re
import sys
import wave

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from app.models import Recording

AUDIO = re.compile(r'bark_audio_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.wav')


def recording_path(directory: Path, name: str) -> Path:
    if not AUDIO.fullmatch(name):
        raise FileNotFoundError(name)
    path = directory / 'recordings' / name
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(name)
    return path


def index_recording(database, path: Path) -> bool:
    match = AUDIO.fullmatch(path.name)
    if not match or path.is_symlink():
        return False
    try:
        timestamp = dt.datetime.strptime(match[1] + ' ' + match[2], '%Y-%m-%d %H-%M-%S')
        stat = path.stat()
        with wave.open(str(path)) as audio:
            duration = audio.getnframes() / audio.getframerate()
    except (ValueError, OSError, EOFError, wave.Error, ZeroDivisionError):
        return False
    values = dict(name=path.name, date=match[1], time=timestamp.strftime('%H:%M:%S'),
                  duration=round(duration, 1), size=stat.st_size, modified=stat.st_mtime_ns)
    statement = insert(Recording).values(**values)
    with database.session.begin() as session:
        session.execute(statement.on_conflict_do_update(index_elements=['name'], set_=values))
    return True


def sync_recordings(database) -> int:
    """Run at startup or via CLI, never while serving dashboard requests."""
    with database.session() as session:
        known = set(session.scalars(select(Recording.name)))
    valid = set()
    for path in (database.directory / 'recordings').glob('bark_audio_*.wav'):
        if index_recording(database, path):
            valid.add(path.name)
    with database.session.begin() as session:
        # A recording inserted concurrently after our scan starts must survive.
        for name in known - valid:
            session.execute(delete(Recording).where(Recording.name == name))
    return len(valid)


@lru_cache(maxsize=64)
def recording_levels(path, modified, size):
    """Read PCM16 audio in bounded blocks, caching only a compact envelope."""
    with wave.open(str(path)) as audio:
        if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('Unsupported audio format')
        frames, rate = audio.getnframes(), audio.getframerate()
        step = max(1, math.ceil(frames / 600))
        levels = []
        for start in range(0, frames, step):
            remaining = min(step, frames - start)
            peak = 0
            while remaining:
                block = min(remaining, 16384)
                samples = array('h', audio.readframes(block))
                if sys.byteorder != 'little':
                    samples.byteswap()
                peak = max(peak, max((abs(sample) for sample in samples), default=0))
                remaining -= block
            levels.append(round(max(-60, 20 * math.log10(peak / 32768)) if peak else -60, 1))
    return dict(duration=frames/rate, step=step/rate, levels=levels,
                peak_dbfs=max(levels, default=-60))
