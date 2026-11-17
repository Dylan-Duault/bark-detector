import datetime as dt
import unittest
from unittest.mock import Mock
from app.services.sessions import SessionTracker


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.history = Mock()
        self.tracker = SessionTracker(self.history)
        self.start = dt.datetime(2026, 11, 14, 12)

    def update(self, bark, seconds):
        self.tracker.update(bark, self.start + dt.timedelta(seconds=seconds), seconds)

    def test_short_pause_stays_in_series_and_quiet_gap_finishes_it(self):
        self.update(True, 0)
        self.update(True, 2)
        self.update(False, 50)
        self.history.bark_session.assert_not_called()
        self.update(False, 93)
        self.history.bark_session.assert_called_once_with(self.start, self.start + dt.timedelta(seconds=2), 2, 2)

    def test_shutdown_records_actual_duration_without_subtracting_quiet_gap(self):
        self.update(True, 0)
        self.update(True, 4)
        self.tracker.finish()
        self.tracker.finish()
        self.assertEqual(self.history.bark_session.call_count, 1)
        self.assertEqual(self.history.bark_session.call_args.args[2:], (4, 2))

    def test_isolated_detection_does_not_make_a_series(self):
        self.update(True, 0)
        self.update(False, 91)
        self.history.bark_session.assert_not_called()

    def test_new_detection_after_gap_belongs_to_a_new_series(self):
        for second in (0, 2, 95, 97):
            self.update(True, second)
        self.tracker.finish()
        self.assertEqual(self.history.bark_session.call_count, 2)
