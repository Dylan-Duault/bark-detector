from pathlib import Path
import unittest
from install_services import ROOT, SERVICES, render


class ServiceTests(unittest.TestCase):
    def test_templates_use_current_project_and_non_root_account(self):
        for name in SERVICES:
            with self.subTest(name=name):
                unit = render((ROOT / 'systemd' / name).read_text(), 'pi', Path('/home/pi/dog journal'))
                self.assertIn('User=pi\n', unit)
                self.assertIn(r'WorkingDirectory=/home/pi/dog\x20journal', unit)
                self.assertIn('ExecStart="/home/pi/dog journal/.venv/bin/python"', unit)
                self.assertIn('Restart=always', unit)
                self.assertIn('WantedBy=multi-user.target', unit)
                self.assertNotIn('@', unit)


if __name__ == '__main__':
    unittest.main()
