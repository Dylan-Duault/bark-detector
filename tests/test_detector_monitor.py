import datetime as dt
from pathlib import Path
import tempfile
import unittest

from detector_monitor import DetectorMonitor, read_monitoring
from web_server import dashboard_data


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.now = [dt.datetime(2026, 11, 14, 12).timestamp()]
        self.monitor = DetectorMonitor(self.directory, clock=lambda:self.now[0], monotonic=lambda:self.now[0])

    def tearDown(self):
        self.monitor.close()
        self.tmp.cleanup()

    def test_model_loading_and_no_microphone_do_not_count_as_listening(self):
        self.now[0] += 100
        self.monitor.heartbeat()
        self.monitor.set_state('microphone_unavailable')
        status, coverage = read_monitoring(self.directory, self.now[0])
        self.assertEqual(status['state'], 'microphone_unavailable')
        self.assertIsNone(status['last_audio_at'])
        self.assertEqual(sum(coverage['2026-11-14']), 0)

    def test_only_processed_samples_are_counted_and_overlap_is_not_double_counted(self):
        self.monitor.processed(self.now[0], 1.2)
        self.now[0] += .6
        self.monitor.processed(self.now[0], 1.2)
        self.now[0] += 100
        self.monitor.heartbeat()
        status, coverage = read_monitoring(self.directory, self.now[0])
        self.assertEqual(status['state'], 'no_audio')
        self.assertAlmostEqual(sum(coverage['2026-11-14']), 1.8, places=5)

    def test_loss_of_heartbeat_cannot_show_listening_forever(self):
        self.monitor.processed(self.now[0], 1.2)
        status, _ = read_monitoring(self.directory, self.now[0]+21)
        self.assertEqual(status['state'], 'unresponsive')
        self.monitor.set_state('stopped')
        status, _ = read_monitoring(self.directory, self.now[0]+100)
        self.assertEqual(status['state'], 'stopped')

    def test_midnight_splits_coverage_and_restart_preserves_duration(self):
        end = dt.datetime(2026, 11, 15, 0, 0, 1).timestamp()
        self.now[0] = end
        self.monitor.processed(end, 2)
        self.monitor.close()
        self.monitor = DetectorMonitor(self.directory, clock=lambda:self.now[0], monotonic=lambda:self.now[0])
        status, coverage = read_monitoring(self.directory, end)
        self.assertAlmostEqual(coverage['2026-11-14'][23], 1)
        self.assertAlmostEqual(coverage['2026-11-15'][0], 1)
        self.assertEqual(status['last_audio_at'], end)
        self.assertLess(status['tracking_since'], end)

    def test_api_includes_coverage_even_without_barks_and_keeps_old_days_unknown(self):
        self.monitor.processed(self.now[0], 1.2)
        result = dashboard_data(self.directory, '2026-11-14')
        self.assertAlmostEqual(result['summary']['listened_seconds'], 1.2, places=5)
        self.assertTrue(result['summary']['has_data'])
        self.assertEqual(result['summary']['detections'], 0)
        self.assertIsNone(result['trends']['days'][0]['listened_seconds'])
        self.assertFalse(result['trends']['days'][0]['has_data'])
        self.assertAlmostEqual(result['trends']['listened_seconds'], 1.2, places=5)
        self.assertIsNone(dashboard_data(self.directory, '2026-10-01')['summary']['listened_seconds'])

    def test_reading_a_missing_database_does_not_create_it(self):
        missing = self.directory/'other'
        state, coverage = read_monitoring(missing)
        self.assertEqual(state['state'], 'unknown')
        self.assertEqual(coverage, {})
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
