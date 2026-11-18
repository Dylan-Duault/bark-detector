"""Rerunnable import of append-only v1 logs; original files remain untouched."""
from contextlib import closing
import datetime as dt
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from app.models import BarkSession, Coverage, Day, Detection, DetectorState, LegacyImport, MusicEvent
from app.services.recordings import sync_recordings
from app.infrastructure.paths import prepare_data_directory

BARK = re.compile(r'^\[BARKING DETECTED\] (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}).*volume: ([\d.]+)')
SESSION = re.compile(r'^\[BARK SESSION\] From (.*?) to (.*?) \(Duration: ([\d.]+) seconds, (\d+) barks\)')


def legacy_files(directory):
    return sorted((directory / 'logs').glob('bark_log_????-??-??.txt')) + sorted(
        (directory / 'logs').glob('music_????-??-??.jsonl'))


def parse_file(path):
    """Yield only complete, valid records with stable source/line identifiers."""
    date = path.stem.removeprefix('bark_log_').removeprefix('music_')
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return
    with path.open(encoding='utf-8', errors='replace') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.endswith('\n'):
                continue  # Retry a line still being written on the next import.
            values = dict(date=date, legacy_key=f'{path.name}:{line_number}')
            try:
                if path.suffix == '.jsonl':
                    event = json.loads(line)
                    if (not isinstance(event, dict) or event.get('status') not in ('started', 'failed')
                            or not all(isinstance(event.get(key), str) for key in ('time', 'track', 'detail'))):
                        continue
                    dt.time.fromisoformat(event['time'])
                    yield MusicEvent, dict(values, **{key: event[key] for key in ('time', 'track', 'status', 'detail')})
                elif match := BARK.match(line):
                    timestamp = dt.datetime.fromisoformat(match[1] + 'T' + match[2])
                    if match[1] != date:
                        continue
                    yield Detection, dict(values, hour=timestamp.hour, occurred_at=timestamp.isoformat(), volume=float(match[3]))
                elif match := SESSION.match(line):
                    start, end = (dt.datetime.fromisoformat(match[i]) for i in (1, 2))
                    seconds = float(match[3])
                    if not math.isfinite(seconds):
                        continue
                    yield BarkSession, dict(values, started_at=start.isoformat(), ended_at=end.isoformat(), seconds=seconds, count=int(match[4]))
            except (ValueError, TypeError):
                continue


def backup_legacy(directory):
    """Snapshot metadata before first import; WAV originals are retained in place."""
    target = directory / 'backups' / 'before-v2'
    if (target / 'complete.json').exists():
        return target
    paths = legacy_files(directory)
    monitor = directory / 'monitoring.sqlite3'
    if not paths and not monitor.exists():
        return None
    target.mkdir(parents=True, exist_ok=True)
    (target / 'logs').mkdir(exist_ok=True)
    for path in paths:
        shutil.copy2(path, target / 'logs' / path.name)
    if monitor.exists():
        with closing(sqlite3.connect(monitor.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(target / monitor.name)) as destination:
                source.backup(destination)
    (target / 'complete.json').write_text(json.dumps(dict(
        created_at=dt.datetime.now().isoformat(), logs=len(paths),
        audio='Original WAV files retained unchanged in data/recordings'), indent=2))
    return target


def import_monitoring(database):
    path = database.directory / 'monitoring.sqlite3'
    if not path.exists():
        return
    with database.session.begin() as session:
        if session.get(LegacyImport, path.name):
            return
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
            source.row_factory = sqlite3.Row
            for table, model in (('coverage', Coverage), ('detector', DetectorState)):
                for row in source.execute(f'SELECT * FROM {table}'):
                    # Existing v2 measurements always take precedence.
                    session.execute(insert(model).values(**dict(row)).on_conflict_do_nothing())
        session.add(LegacyImport(path=path.name, signature='imported-once'))


def import_logs(database):
    for path in legacy_files(database.directory):
        stat = path.stat()
        signature = f'{stat.st_size}:{stat.st_mtime_ns}'
        with database.session.begin() as session:
            previous = session.get(LegacyImport, path.name)
            if previous and previous.signature == signature:
                continue
            date = path.stem.removeprefix('bark_log_').removeprefix('music_')
            try:
                dt.date.fromisoformat(date)
            except ValueError:
                continue
            if path.suffix == '.txt':
                session.execute(insert(Day).values(date=date, has_log=True)
                                .on_conflict_do_update(index_elements=['date'], set_={'has_log': True}))
            for model, values in parse_file(path):
                session.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=['legacy_key']))
                session.execute(insert(Day).values(date=date, has_log=True).on_conflict_do_nothing())
            session.merge(LegacyImport(path=path.name, signature=signature))


def verify_legacy(database):
    """Compare imported records and session durations to their legacy sources."""
    expected = {model: 0 for model in (Detection, BarkSession, MusicEvent)}
    seconds = 0.0
    for path in legacy_files(database.directory):
        for model, values in parse_file(path):
            expected[model] += 1
            if model is BarkSession:
                seconds += values['seconds']
    with database.session() as session:
        actual = {model: session.scalar(select(func.count()).select_from(model).where(model.legacy_key.is_not(None))) for model in expected}
        actual_seconds = session.scalar(select(func.sum(BarkSession.seconds)).where(BarkSession.legacy_key.is_not(None))) or 0
    report = {model.__tablename__: dict(source=expected[model], imported=actual[model]) for model in expected}
    report['session_seconds'] = dict(source=seconds, imported=actual_seconds)
    report['ok'] = actual == expected and math.isclose(seconds, actual_seconds, abs_tol=.001)
    return report


def initialize(database):
    """Called once per process startup, serialized across processes."""
    with database.maintenance():
        prepare_data_directory(database.directory)
        backup = backup_legacy(database.directory)
        database.upgrade()
        import_logs(database)
        import_monitoring(database)
        recordings = sync_recordings(database)
    return dict(backup=str(backup) if backup else None, recordings=recordings)
