"""End-to-end detector coordination with a fake microphone and classifier."""
import datetime as dt
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from app.config import Settings
from app.detector import run
from app.infrastructure.database import Database
from app.services.dashboard import Dashboard
from app.services.migration import initialize
from app.services.monitoring import DetectorMonitor


class DetectorTests(unittest.TestCase):
    def test_stopped_microphone_stream_fails_so_systemd_can_restart(self):
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            settings = Settings(_env_file=None, data_dir=directory, bark_music_enabled=False)
            database = Database(directory)
            initialize(database)
            monitor = DetectorMonitor(directory, database=database)
            buffer = Mock()
            buffer.read_chunk.return_value = None
            stream = Mock(active=False)
            try:
                with patch('sounddevice.InputStream', return_value=stream), \
                     patch('app.infrastructure.yamnet.Yamnet'), \
                     patch('app.services.recording.AudioBuffer', return_value=buffer):
                    with self.assertRaisesRegex(RuntimeError, 'Microphone stream stopped'):
                        run(settings, database, monitor)
                self.assertEqual(monitor.state, 'microphone_unavailable')
                stream.stop.assert_called_once()
                stream.close.assert_called_once()
            finally:
                monitor.close()
                database.close()

    def test_clean_shutdown_publishes_audio_series_and_monitoring(self):
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            settings = Settings(_env_file=None, data_dir=directory, bark_music_enabled=False)
            database = Database(directory)
            initialize(database)
            monitor = DetectorMonitor(directory, database=database)
            buffer = Mock(last_chunk_end=time.time())
            chunk = np.full(19200, .1, dtype=np.float32)
            buffer.read_chunk.side_effect = [chunk, chunk, KeyboardInterrupt]
            buffer.start_capture.return_value = [chunk]
            buffer.drain_capture.return_value = []
            stream = Mock()
            model = Mock()
            model.classify.return_value = (True, .1)
            try:
                with patch('sounddevice.InputStream', return_value=stream), \
                     patch('app.infrastructure.yamnet.Yamnet', return_value=model), \
                     patch('app.services.recording.AudioBuffer', return_value=buffer):
                    with self.assertRaises(KeyboardInterrupt):
                        run(settings, database, monitor)
                result = Dashboard(database).snapshot(dt.date.today().isoformat())
                self.assertEqual(result['summary']['detections'], 2)
                self.assertEqual(result['summary']['sessions'], 1)
                self.assertEqual(result['summary']['recordings'], 1)
                self.assertGreater(result['summary']['listened_seconds'], 0)
                self.assertEqual(list((directory / 'recordings').glob('*.part')), [])
                stream.stop.assert_called_once()
                stream.close.assert_called_once()
            finally:
                monitor.close()
                database.close()
