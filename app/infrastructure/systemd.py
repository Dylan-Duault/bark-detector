"""Install and enable Raspberry Pi systemd services. Run with sudo."""
import os
from pathlib import Path
import pwd
import subprocess
from app.config import ROOT, Settings

TEMPLATES = Path(__file__).resolve().parents[1] / 'assets/systemd'
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


def install_services(user, output_dir=None):
    """Install as root, or generate a preview without changing running services."""
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        raise ValueError(f'Unknown service account: {user}') from None
    if account.pw_uid == 0:
        raise ValueError('Choose a non-root account with --user')
    if not (ROOT / '.venv/bin/python').exists():
        raise ValueError('Create .venv and install requirements.txt first')
    if not output_dir:
        Settings().require_pin()
    if not output_dir and os.geteuid() != 0:
        raise PermissionError('Run with sudo, or use --output-dir to preview the units')
    target = output_dir or Path('/etc/systemd/system')
    if not output_dir:
        # Stop the old units before replacing them, avoiding stale-unit warnings.
        installed = [name for name in SERVICES if (target / name).exists()]
        if installed:
            subprocess.run(['systemctl', 'stop', *installed], check=True)
    target.mkdir(parents=True, exist_ok=True)
    for name in SERVICES:
        template = (TEMPLATES / name).read_text()
        (target / name).write_text(render(template, user, ROOT))
        print('Written:', target / name, flush=True)
    if not output_dir:
        # The service account must own SQLite, its WAL and the migration lock.
        subprocess.run(['runuser', '-u', user, '--', str(ROOT / '.venv/bin/python'),
                        '-m', 'app.cli', 'migrate'], cwd=ROOT, check=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', *SERVICES], check=True)
        subprocess.run(['systemctl', 'restart', *SERVICES], check=True)
        print('Both services are enabled at boot and started now.')
