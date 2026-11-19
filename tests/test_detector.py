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
from app.services.monitoring import DetectorMonitor, read_monitoring


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

    def test_active_microphone_without_samples_fails_after_five_seconds(self):
        for delivers_samples in (False, True):
            with self.subTest(delivers_samples=delivers_samples), tempfile.TemporaryDirectory() as scratch:
                directory = Path(scratch)
                settings = Settings(_env_file=None, data_dir=directory, bark_music_enabled=False)
                database = Database(directory)
                initialize(database)
                monitor = DetectorMonitor(directory, database=database)
                stream = Mock(active=True)
                model = Mock()
                model.classify.return_value = (False, 0)
                clock = Mock(wraps=time)
                tick = 0
                clock.monotonic.side_effect = lambda: tick
                silence = np.zeros((19200, 1), dtype=np.float32)

                def advance(_):
                    nonlocal tick
                    tick += 1
                    if delivers_samples and tick == 4:
                        callback = input_stream.call_args.kwargs['callback']
                        callback(silence, len(silence), None, None)

                clock.sleep.side_effect = advance
                try:
                    with patch('sounddevice.InputStream', return_value=stream) as input_stream, \
                         patch('app.infrastructure.yamnet.Yamnet', return_value=model), \
                         patch('app.detector.time', clock), patch('app.services.recording.time', clock):
                        with self.assertRaisesRegex(RuntimeError, 'No microphone samples for 5 seconds'):
                            run(settings, database, monitor)
                    self.assertEqual(tick, 9 if delivers_samples else 5)
                    self.assertEqual(model.classify.call_count, int(delivers_samples))
                    status, _ = read_monitoring(directory)
                    self.assertEqual(status['state'], 'no_audio')
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
            buffer = Mock(last_chunk_end=time.time(), last_input_tick=None)
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
