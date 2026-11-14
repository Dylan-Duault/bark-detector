"""Persist detector health and the duration of audio actually analysed."""
import datetime as dt
import math
from pathlib import Path
import sqlite3
import time

DATABASE = 'monitoring.sqlite3'
FLUSH_SECONDS = 5
STALE_SECONDS = 20


class DetectorMonitor:
    def __init__(self, directory, clock=time.time, monotonic=time.monotonic):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.monotonic = monotonic
        self.connection = sqlite3.connect(self.directory / DATABASE)
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS detector (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state TEXT NOT NULL,
                updated_at REAL NOT NULL,
                last_audio_at REAL,
                tracking_since REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coverage (
                date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                seconds REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (date, hour)
            );
        ''')
        self.pending = {}
        self.last_audio_at = None
        self.last_credited_end = None
        self.last_flush = float('-inf')
        self.state = 'starting'
        self.state_since = self.monotonic()
        self.set_state('starting')

    def set_state(self, state):
        self.state = state
        self.state_since = self.monotonic()
        self.flush(force=True)

    def processed(self, end, seconds):
        """Credit only successfully classified audio, never process uptime."""
        start = end - seconds
        if self.last_credited_end is not None:
            start = max(start, self.last_credited_end)
        # Split at whole seconds so local hour/day boundaries and DST are respected.
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
        now = self.clock()
        if self.state == 'listening' and now - self.last_audio_at > 5:
            self.set_state('no_audio')
        elif self.state == 'waiting_audio' and self.monotonic() - self.state_since > 5:
            self.set_state('no_audio')
        self.flush()

    def flush(self, force=False):
        tick = self.monotonic()
        if not force and tick - self.last_flush < FLUSH_SECONDS:
            return
        now = self.clock()
        local = dt.datetime.fromtimestamp(now)
        with self.connection:
            self.connection.execute('''
                INSERT INTO detector VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET state=excluded.state,
                    updated_at=excluded.updated_at, last_audio_at=COALESCE(excluded.last_audio_at, detector.last_audio_at)
            ''', (self.state, now, self.last_audio_at, now))
            self.connection.execute('INSERT OR IGNORE INTO coverage VALUES (?, ?, 0)',
                                    (local.date().isoformat(), local.hour))
            self.connection.executemany('''
                INSERT INTO coverage VALUES (?, ?, ?)
                ON CONFLICT(date, hour) DO UPDATE SET seconds=seconds+excluded.seconds
            ''', [(date, hour, seconds) for (date, hour), seconds in self.pending.items()])
        self.pending.clear()
        self.last_flush = tick

    def close(self):
        try:
            self.flush(force=True)
        finally:
            self.connection.close()


def read_monitoring(directory, now=None):
    """Read-only access: browsing the dashboard must not create measurement data."""
    unknown = dict(state='unknown', updated_at=None, last_audio_at=None, tracking_since=None)
    path = Path(directory).resolve() / DATABASE
    if not path.exists():
        return unknown, {}
    try:
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.5)
        try:
            connection.row_factory = sqlite3.Row
            row = connection.execute('SELECT * FROM detector WHERE id=1').fetchone()
            coverage = {}
            for item in connection.execute('SELECT date, hour, seconds FROM coverage'):
                coverage.setdefault(item['date'], [0.0]*24)[item['hour']] = item['seconds']
        finally:
            connection.close()
    except sqlite3.Error:
        return unknown, {}
    if row is None:
        return unknown, coverage
    status = {key: row[key] for key in unknown}
    elapsed = (time.time() if now is None else now) - status['updated_at']
    limit = 120 if status['state'] == 'starting' else STALE_SECONDS
    if status['state'] in ('starting', 'listening', 'waiting_audio', 'no_audio') and elapsed > limit:
        status['state'] = 'unresponsive'
    return status, coverage
