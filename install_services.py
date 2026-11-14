"""Install and enable Raspberry Pi systemd services. Run with sudo."""
import argparse
import os
from pathlib import Path
import pwd
import subprocess

ROOT = Path(__file__).resolve().parent
SERVICES = ('bark-detector.service', 'bark-dashboard.service')


def quote(value):
    # systemd performs specifier expansion even inside quoted paths.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def render(template, user, project):
    # Quote each ExecStart argument independently, including the complete script path.
    directory = str(project).replace('\\', r'\x5c').replace('%', '%%').replace(' ', r'\x20')
    result = template.replace('@USER@', user).replace('@PROJECT@', directory)
    result = result.replace('@PYTHON@', quote(project / '.venv/bin/python'))
    for script in ('bark_session_logger.py', 'web_server.py'):
        result = result.replace('@PROJECT_ARG@/'+script, quote(project / script))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', default=os.environ.get('SUDO_USER') or pwd.getpwuid(os.getuid()).pw_name)
    parser.add_argument('--output-dir', type=Path, help='Generate units here without installation (no sudo required)')
    args = parser.parse_args()
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0:
        parser.error('Choose a non-root account with --user')
    if not (ROOT / '.venv/bin/python').exists():
        parser.error('Create .venv and install requirements.txt first')
    if not args.output_dir and os.geteuid() != 0:
        parser.error('Run with sudo, or use --output-dir to preview the units')
    target = args.output_dir or Path('/etc/systemd/system')
    target.mkdir(parents=True, exist_ok=True)
    for name in SERVICES:
        template = (ROOT / 'systemd' / name).read_text()
        (target / name).write_text(render(template, args.user, ROOT))
        print('Written:', target / name)
    if not args.output_dir:
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', *SERVICES], check=True)
        subprocess.run(['systemctl', 'restart', *SERVICES], check=True)
        print('Both services are enabled at boot and started now.')


if __name__ == '__main__':
    main()
