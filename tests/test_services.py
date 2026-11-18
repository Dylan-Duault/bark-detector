from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from app.infrastructure.systemd import SERVICES, TEMPLATES, default_user, install_services, render


class ServiceTests(unittest.TestCase):
    def test_preview_generates_both_units_without_touching_services(self):
        with tempfile.TemporaryDirectory() as scratch:
            project = Path(scratch) / 'project'
            python = project / '.venv/bin/python'
            python.parent.mkdir(parents=True)
            python.touch()
            output = Path(scratch) / 'preview'
            with patch('app.infrastructure.systemd.ROOT', project), \
                 patch('app.infrastructure.systemd.pwd.getpwnam', return_value=Mock(pw_uid=1000)), \
                 patch('app.infrastructure.systemd.subprocess.run') as run:
                install_services('pi', output)
            run.assert_not_called()
            self.assertEqual({path.name for path in output.iterdir()}, set(SERVICES))
            for name in SERVICES:
                unit = (output / name).read_text()
                self.assertIn('User=pi\n', unit)
                self.assertIn(f'WorkingDirectory={project}', unit)
                self.assertNotIn('@', unit)

    def test_cli_routes_installation_to_the_installer(self):
        from app.cli import main
        with patch('app.infrastructure.systemd.install_services') as install:
            main(['install-services', '--user', 'pi', '--output-dir', '/tmp/preview'])
        install.assert_called_once_with('pi', Path('/tmp/preview'))

    def test_root_shell_uses_non_root_project_owner(self):
        with patch.dict('os.environ', {'SUDO_USER': 'root'}), \
             patch('app.infrastructure.systemd.os.getuid', return_value=0), \
             patch('app.infrastructure.systemd.ROOT') as project, \
             patch('app.infrastructure.systemd.pwd.getpwnam', return_value=Mock(pw_uid=0)), \
             patch('app.infrastructure.systemd.pwd.getpwuid', return_value=Mock(pw_name='pi')):
            project.stat.return_value.st_uid = 1000
            self.assertEqual(default_user(), 'pi')

    def test_templates_use_current_project_and_non_root_account(self):
        for name in SERVICES:
            with self.subTest(name=name):
                unit = render((TEMPLATES / name).read_text(), 'pi', Path('/home/pi/dog journal'))
                self.assertIn('User=pi\n', unit)
                self.assertIn(r'WorkingDirectory=/home/pi/dog\x20journal', unit)
                self.assertIn('ExecStart="/home/pi/dog journal/.venv/bin/python"', unit)
                self.assertIn('Restart=always', unit)
                self.assertIn('WantedBy=multi-user.target', unit)
                self.assertNotIn('@', unit)


if __name__ == '__main__':
    unittest.main()
