from pathlib import Path
import tempfile
import unittest

from app.infrastructure.paths import prepare_data_directory
from app.services.dashboard import dashboard_data


class StorageTests(unittest.TestCase):
    def test_initialization_is_idempotent_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as scratch:
            data = Path(scratch) / 'data'
            prepare_data_directory(data)
            log = data / 'logs' / 'bark_log_2026-11-14.txt'
            content = '[BARKING DETECTED] 2026-11-14 08:10:00 detected (volume: 0.0420)\n'
            log.write_text(content)
            prepare_data_directory(data)
            self.assertEqual(log.read_text(), content)
            self.assertTrue((data / 'recordings').is_dir())
            result = dashboard_data(data, '2026-11-14')
            self.assertEqual(result['summary']['detections'], 1)
            self.assertTrue(result['trends']['days'][-1]['has_log'])
            self.assertEqual(list(data.glob('bark_log_*.txt')), [])


if __name__ == '__main__':
    unittest.main()
