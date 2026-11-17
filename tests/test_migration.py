"""Migration safety and data parity, using isolated v1 fixtures."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.infrastructure.database import Database
from app.models import Coverage, DetectorState
from app.services.dashboard import Dashboard
from app.services.history import History
from app.services.migration import initialize, verify_legacy


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory / 'logs').mkdir()
        (self.directory / 'recordings').mkdir()
        self.log = self.directory / 'logs/bark_log_2026-11-14.txt'
        self.log.write_text('[BARKING DETECTED] 2026-11-14 08:00:00 detected (volume: 0.1200)\n'
                            '[BARK SESSION] From 2026-11-14 08:00:00 to 2026-11-14 08:01:32 (Duration: 2.0 seconds, 2 barks)\n')
        self.database = Database(self.directory)
        self.addCleanup(self.database.close)

    def test_backup_import_parity_and_repeated_runs(self):
        original = self.log.read_bytes()
        first = initialize(self.database)
        self.assertEqual(Path(first['backup'], 'logs', self.log.name).read_bytes(), original)
        initialize(self.database)
        report = verify_legacy(self.database)
        self.assertTrue(report['ok'])
        self.assertEqual(report['detections'], {'source':1, 'imported':1})
        self.assertEqual(report['session_seconds'], {'source':2, 'imported':2})
        self.assertEqual(self.log.read_bytes(), original)

    def test_appended_and_previously_incomplete_lines_are_imported_once(self):
        initialize(self.database)
        with self.log.open('a') as stream:
            stream.write('[BARKING DETECTED] 2026-11-14 09:00:00 detected (volume: 0.2000)')
        initialize(self.database)
        self.assertEqual(Dashboard(self.database).snapshot('2026-11-14')['summary']['detections'], 1)
        with self.log.open('a') as stream:
            stream.write('\n')
        initialize(self.database)
        initialize(self.database)
        self.assertEqual(Dashboard(self.database).snapshot('2026-11-14')['summary']['detections'], 2)
        self.assertTrue(verify_legacy(self.database)['ok'])

    def test_legacy_monitoring_preserves_coverage_and_never_overwrites_v2(self):
        with closing(sqlite3.connect(self.directory / 'monitoring.sqlite3')) as source:
            source.executescript('CREATE TABLE detector(id INTEGER PRIMARY KEY, state TEXT, updated_at REAL, last_audio_at REAL, tracking_since REAL);'
                                 'CREATE TABLE coverage(date TEXT, hour INTEGER, seconds REAL);'
                                 "INSERT INTO detector VALUES(1, 'stopped', 10, 9, 1);"
                                 "INSERT INTO coverage VALUES('2026-11-14', 8, 12.5);")
        initialize(self.database)
        with self.database.session.begin() as session:
            self.assertEqual(session.get(Coverage, ('2026-11-14', 8)).seconds, 12.5)
            self.assertEqual(session.get(DetectorState, 1).tracking_since, 1)
            session.get(Coverage, ('2026-11-14', 8)).seconds += 5
        initialize(self.database)
        with self.database.session() as session:
            self.assertEqual(session.get(Coverage, ('2026-11-14', 8)).seconds, 17.5)

    def test_dashboard_uses_database_without_reading_legacy_logs(self):
        initialize(self.database)
        History(self.database).detection(dt.datetime(2026, 11, 14, 10), .3)
        with patch('pathlib.Path.open', side_effect=AssertionError('No file access during requests')):
            data = Dashboard(self.database).snapshot('2026-11-14')
        self.assertEqual(data['summary']['detections'], 2)
        self.assertEqual(data['summary']['hours'][10], 1)

    def test_music_import_skips_malformed_lines_and_does_not_duplicate(self):
        path = self.directory / 'logs/music_2026-11-14.jsonl'
        path.write_text(json.dumps(dict(time='12:00:00', track='calm.mp3', status='started', detail=''))+'\ninvalid\n')
        initialize(self.database)
        initialize(self.database)
        self.assertEqual(len(Dashboard(self.database).snapshot('2026-11-14')['music_events']), 1)
        self.assertTrue(verify_legacy(self.database)['ok'])
