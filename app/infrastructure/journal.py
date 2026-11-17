"""Bounded access to the two application systemd journals."""
import json
import subprocess


def live_logs(source, run=subprocess.run):
    units = {'detector': 'bark-detector.service', 'dashboard': 'bark-dashboard.service'}
    if source not in units:
        raise ValueError('Source de logs inconnue')
    result = run(['journalctl', '--quiet', '--no-pager', '--output=json',
                  '--lines=200', '--unit=' + units[source]],
                 capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise OSError('Lecture du journal indisponible.')
    entries = []
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
            message = item.get('MESSAGE')
            if not isinstance(message, str):
                continue
            entries.append(dict(id=item['__CURSOR'],
                timestamp=int(item['__REALTIME_TIMESTAMP']) / 1000000,
                message=message[:16000], priority=str(item.get('PRIORITY', '6'))))
        except (ValueError, KeyError, TypeError):
            continue
    return dict(entries=entries, source=source)
