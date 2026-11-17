"""Install and enable Raspberry Pi systemd services. Run with sudo."""
import argparse
import os
from pathlib import Path
import pwd
import subprocess
from app.config import Settings

ROOT = Path(__file__).resolve().parent
SERVICES = ('bark-detector.service', 'bark-dashboard.service')


def default_user():
    """Prefer the sudo caller, then the current user, then the project owner."""
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        try:
            account = pwd.getpwnam(sudo_user)
            if account.pw_uid != 0:
                return account.pw_name
        except KeyError:
            pass
    for uid in (os.getuid(), ROOT.stat().st_uid):
        if uid != 0:
            return pwd.getpwuid(uid).pw_name
    return 'root'  # A root-owned checkout still requires an explicit --user.


def quote(value):
    # systemd performs specifier expansion even inside quoted paths.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def render(template, user, project):
    # Quote paths independently; module entry points run from WorkingDirectory.
    directory = str(project).replace('\\', r'\x5c').replace('%', '%%').replace(' ', r'\x20')
    result = template.replace('@USER@', user).replace('@PROJECT@', directory)
    result = result.replace('@PYTHON@', quote(project / '.venv/bin/python'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', default=default_user())
    parser.add_argument('--output-dir', type=Path, help='Generate units here without installation (no sudo required)')
    args = parser.parse_args()
    try:
        account = pwd.getpwnam(args.user)
    except KeyError:
        parser.error(f'Unknown service account: {args.user}')
    if account.pw_uid == 0:
        parser.error('Choose a non-root account with --user')
    if not (ROOT / '.venv/bin/python').exists():
        parser.error('Create .venv and install requirements.txt first')
    if not args.output_dir:
        try:
            Settings().require_pin()
        except ValueError as error:
            parser.error(str(error))
    if not args.output_dir and os.geteuid() != 0:
        parser.error('Run with sudo, or use --output-dir to preview the units')
    target = args.output_dir or Path('/etc/systemd/system')
    if not args.output_dir:
        # Stop the old units before replacing them, avoiding stale-unit warnings.
        installed = [name for name in SERVICES if (target / name).exists()]
        if installed:
            subprocess.run(['systemctl', 'stop', *installed], check=True)
    target.mkdir(parents=True, exist_ok=True)
    for name in SERVICES:
        template = (ROOT / 'systemd' / name).read_text()
        (target / name).write_text(render(template, args.user, ROOT))
        print('Written:', target / name, flush=True)
    if not args.output_dir:
        # The service account must own SQLite, its WAL and the migration lock.
        subprocess.run(['runuser', '-u', args.user, '--', str(ROOT / '.venv/bin/python'),
                        '-m', 'app.cli', 'migrate'], cwd=ROOT, check=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', *SERVICES], check=True)
        subprocess.run(['systemctl', 'restart', *SERVICES], check=True)
        print('Both services are enabled at boot and started now.')


if __name__ == '__main__':
    main()
