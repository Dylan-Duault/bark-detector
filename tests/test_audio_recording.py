import datetime as dt
from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

from audio_recording import AudioBuffer, BarkRecorder


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.buffer = AudioBuffer(sample_rate=10, chunk_samples=10, history_seconds=3)
        self.recorder = BarkRecorder(self.buffer, self.directory, sample_rate=10)
        self.timestamp = dt.datetime(2026, 11, 14, 20, 0, 0)

    def tearDown(self):
        self.recorder.finish()
        self.tmp.cleanup()

    def feed(self, value):
        self.buffer.callback(np.full((10, 1), value, dtype=np.float32), 10, None, None)

    def update(self, bark, now):
        self.recorder.update(bark, now, self.timestamp + dt.timedelta(seconds=now))

    def test_isolated_detection_does_not_start_recording(self):
        self.feed(.1)
        self.update(True, 0)
        self.update(False, 1)
        self.update(True, 2)
        self.assertIsNone(self.recorder.writer)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_pretrigger_history_and_tail_have_no_missing_or_duplicate_samples(self):
        for value in (0, .1, .2, .3):
            self.feed(value)
        self.update(True, 0)
        self.update(True, 1)
        self.assertEqual(len(list(self.directory.glob('*.wav'))), 0)
        self.assertEqual(len(list(self.directory.glob('*.wav.part'))), 1)
        self.feed(.4)
        self.update(False, 10.99)
        self.assertIsNotNone(self.recorder.writer)
        self.feed(.5)
        self.update(False, 11)
        self.assertIsNone(self.recorder.writer)
        audio, rate = sf.read(next(self.directory.glob('*.wav')))
        self.assertEqual(rate, 10)
        expected = np.repeat([.1, .2, .3, .4, .5], 10)
        np.testing.assert_allclose(audio, expected, atol=1/32768)
        self.assertEqual(list(self.directory.glob('*.wav.part')), [])

    def test_short_pauses_and_new_detection_extend_same_recording(self):
        self.feed(.1)
        self.update(True, 0)
        self.update(True, 1)
        self.feed(.2)
        self.update(False, 8)
        # A single positive at the boundary extends the active recording.
        self.update(True, 11)
        self.feed(.3)
        self.update(False, 20.9)
        self.assertIsNotNone(self.recorder.writer)
        self.update(False, 21)
        self.assertEqual(len(list(self.directory.glob('*.wav'))), 1)
        self.update(True, 22)
        self.assertIsNone(self.recorder.writer)
        self.update(True, 23)
        self.assertIsNotNone(self.recorder.writer)
        self.recorder.finish()
        self.assertEqual(len(list(self.directory.glob('*.wav'))), 2)

    def test_shutdown_flushes_pending_audio_and_finish_is_idempotent(self):
        self.feed(.1)
        self.update(True, 0)
        self.update(True, 1)
        self.feed(.7)
        self.recorder.finish()
        self.recorder.finish()
        audio, _ = sf.read(next(self.directory.glob('*.wav')))
        np.testing.assert_allclose(audio, np.repeat([.1, .7], 10), atol=1/32768)
        self.assertFalse(self.buffer.capturing)

    def test_long_sequence_streams_to_disk_and_keeps_history_bounded(self):
        self.update(True, 0)
        self.update(True, 1)
        for second in range(2, 202):
            self.feed(.2)
            self.update(True, second)
            self.assertEqual(self.buffer.pending, [])
            self.assertLessEqual(self.buffer.history_length, 30)
        self.recorder.finish()
        self.assertEqual(sf.info(next(self.directory.glob('*.wav'))).frames, 2000)


if __name__ == '__main__':
    unittest.main()
