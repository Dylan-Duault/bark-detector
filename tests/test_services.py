from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from install_services import ROOT, SERVICES, default_user, render


class ServiceTests(unittest.TestCase):
    def test_root_shell_uses_non_root_project_owner(self):
        with patch.dict('os.environ', {'SUDO_USER': 'root'}), \
             patch('install_services.os.getuid', return_value=0), \
             patch('install_services.ROOT') as project, \
             patch('install_services.pwd.getpwnam', return_value=Mock(pw_uid=0)), \
             patch('install_services.pwd.getpwuid', return_value=Mock(pw_name='pi')):
            project.stat.return_value.st_uid = 1000
            self.assertEqual(default_user(), 'pi')

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
