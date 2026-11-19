"""Detector heartbeat and measured audio coverage in the shared application DB."""
import datetime as dt
import math
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.infrastructure.database import Database, DATABASE
from app.models import Coverage, DetectorState
from app.services.migration import initialize

FLUSH_SECONDS = 5
STALE_SECONDS = 20


class DetectorMonitor:
    def __init__(self, directory, clock=time.time, monotonic=time.monotonic, database=None):
        self.database = database or Database(directory)
        self.owns_database = database is None
        if self.owns_database:
            initialize(self.database)
        self.clock, self.monotonic = clock, monotonic
        self.pending = {}
        self.last_audio_at = self.last_credited_end = None
        self.last_flush = float('-inf')
        self.state = 'starting'
        self.set_state('starting')

    def set_state(self, state):
        self.state = state
        self.flush(force=True)

    def processed(self, end, seconds):
        start = max(end - seconds, self.last_credited_end or end - seconds)
        while start < end:
            boundary = min(end, math.floor(start) + 1)
            local = dt.datetime.fromtimestamp(start)
            key = (local.date().isoformat(), local.hour)
            self.pending[key] = self.pending.get(key, 0) + boundary - start
            start = boundary
        self.last_credited_end = max(end, self.last_credited_end or end)
        self.last_audio_at = end
        changed = self.state != 'listening'
        self.state = 'listening'
        self.flush(force=changed)

    def heartbeat(self):
        self.flush()

    def flush(self, force=False):
        tick = self.monotonic()
        if not force and tick - self.last_flush < FLUSH_SECONDS:
            return
        now = self.clock()
        local = dt.datetime.fromtimestamp(now)
        with self.database.session.begin() as session:
            statement = insert(DetectorState).values(id=1, state=self.state, updated_at=now,
                                                     last_audio_at=self.last_audio_at, tracking_since=now)
            session.execute(statement.on_conflict_do_update(index_elements=['id'], set_=dict(
                state=self.state, updated_at=now,
                last_audio_at=statement.excluded.last_audio_at if self.last_audio_at is not None else DetectorState.last_audio_at)))
            session.execute(insert(Coverage).values(date=local.date().isoformat(), hour=local.hour, seconds=0).on_conflict_do_nothing())
            for (date, hour), seconds in self.pending.items():
                statement = insert(Coverage).values(date=date, hour=hour, seconds=seconds)
                session.execute(statement.on_conflict_do_update(index_elements=['date', 'hour'], set_={'seconds': Coverage.seconds + seconds}))
        self.pending.clear()
        self.last_flush = tick

    def close(self):
        try:
            self.flush(force=True)
        finally:
            if self.owns_database:
                self.database.close()


def monitoring_snapshot(session, now=None):
    status = dict(state='unknown', updated_at=None, last_audio_at=None, tracking_since=None)
    row = session.get(DetectorState, 1)
    coverage = {}
    for item in session.scalars(select(Coverage)):
        coverage.setdefault(item.date, [0.0] * 24)[item.hour] = item.seconds
    if row:
        status = {key: getattr(row, key) for key in status}
        elapsed = (time.time() if now is None else now) - status['updated_at']
        limit = 120 if status['state'] == 'starting' else STALE_SECONDS
        if status['state'] in ('starting', 'listening', 'waiting_audio', 'no_audio') and elapsed > limit:
            status['state'] = 'unresponsive'
    return status, coverage


def read_monitoring(directory, now=None):
    from pathlib import Path
    if not (Path(directory) / DATABASE).exists():
        return dict(state='unknown', updated_at=None, last_audio_at=None, tracking_since=None), {}
    database = Database(directory)
    try:
        with database.session() as session:
            return monitoring_snapshot(session, now)
    finally:
        database.close()
