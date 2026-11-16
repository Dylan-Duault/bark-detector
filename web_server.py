"""Local, read-only dashboard for bark logs and recordings (no extra dependencies)."""
from array import array
from functools import lru_cache
import math
import sys
import argparse
import datetime as dt
import json
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
import wave
from dashboard_auth import Auth, COOKIE, SESSION_SECONDS, load_pin
from storage import DATA_DIR, prepare_data_directory
from detector_monitor import read_monitoring

ROOT = Path(__file__).resolve().parent
BARK = re.compile(r'^\[BARKING DETECTED\] (\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\d{2}')
SESSION = re.compile(r'^\[BARK SESSION\].*\(Duration: ([\d.]+) seconds, (\d+) barks\)')
AUDIO = re.compile(r'bark_audio_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.wav')


@lru_cache(maxsize=64)
def recording_levels(path, modified, size):
    """Read PCM16 recordings in bounded blocks; cache only the compact envelope."""
    with wave.open(str(path)) as audio:
        if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('Unsupported audio format')
        frames, rate = audio.getnframes(), audio.getframerate()
        step = max(1, math.ceil(frames / 600))
        levels = []
        for start in range(0, frames, step):
            remaining = min(step, frames - start)
            peak = 0
            while remaining:
                count = min(8192, remaining)
                samples = array('h', audio.readframes(count))
                if sys.byteorder != 'little':
                    samples.byteswap()
                peak = max(peak, max((abs(sample) for sample in samples), default=0))
                remaining -= count
            levels.append(round(max(-60, 20 * math.log10(peak / 32768)), 1) if peak else -60)
        return dict(duration=frames / rate, step=step / rate, levels=levels,
                    peak_dbfs=max(levels, default=-60))


def dashboard_data(directory, selected=None, period=7):
    if period not in (7, 30):
        raise ValueError("Period must be 7 or 30 days")
    detector, coverage = read_monitoring(directory)
    logged_dates = set()
    days = {}
    for path in sorted((directory / 'logs').glob('bark_log_????-??-??.txt')):
        date = path.stem.removeprefix('bark_log_')
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            continue
        logged_dates.add(date)
        day = days.setdefault(date, dict(date=date, detections=0, sessions=0, seconds=0, recordings=0, hours=[0]*24))
        with path.open(encoding='utf-8', errors='replace') as log:
            for line in log:
                bark = BARK.match(line)
                session = SESSION.match(line)
                if bark and bark[1] == date and int(bark[2]) < 24:
                    day['detections'] += 1
                    day['hours'][int(bark[2])] += 1
                elif session:
                    day['sessions'] += 1
                    day['seconds'] += float(session[1])
    recordings = []
    for path in sorted((directory / 'recordings').glob('bark_audio_*.wav'), reverse=True):
        match = AUDIO.fullmatch(path.name)
        if not match or path.is_symlink():
            continue
        try:
            timestamp = dt.datetime.strptime(match[1]+' '+match[2], '%Y-%m-%d %H-%M-%S')
            with wave.open(str(path)) as audio:
                duration = audio.getnframes() / audio.getframerate()
        except (ValueError, OSError, EOFError, wave.Error):
            continue  # A file still being written will appear on the next refresh.
        day = days.setdefault(match[1], dict(date=match[1], detections=0, sessions=0, seconds=0, recordings=0, hours=[0]*24))
        day['recordings'] += 1
        recordings.append(dict(name=path.name, date=match[1], time=timestamp.strftime('%H:%M:%S'), duration=round(duration, 1), url='/audio/'+path.name))
    for key in coverage:
        days.setdefault(key, dict(date=key, detections=0, sessions=0, seconds=0, recordings=0, hours=[0]*24))
    for key, day in days.items():
        day['listened_hours'] = coverage.get(key)
        day['listened_seconds'] = sum(coverage[key]) if key in coverage else None
        day['has_data'] = key in logged_dates or bool(day['listened_seconds'])
    date = selected or dt.date.today().isoformat()
    summary = days.get(date, dict(date=date, detections=0, sessions=0, seconds=0, recordings=0, hours=[0]*24, listened_hours=None, listened_seconds=None, has_data=False))
    end = dt.date.fromisoformat(date)
    trend_days = []
    for offset in range(period-1, -1, -1):
        key = (end - dt.timedelta(days=offset)).isoformat()
        item = days.get(key, dict(date=key, detections=0, sessions=0, seconds=0, recordings=0, hours=[0]*24, listened_hours=None, listened_seconds=None, has_data=False))
        trend_days.append(dict(item, has_log=key in logged_dates))
    trends = dict(period=period, start=trend_days[0]['date'], end=date, days=trend_days,
                  hours=[sum(day['hours'][h] for day in trend_days) for h in range(24)],
                  listened_seconds=sum(day['listened_seconds'] or 0 for day in trend_days) if any(day['listened_seconds'] is not None for day in trend_days) else None)
    return dict(date=date, detector=detector, summary=summary, trends=trends, days=sorted(days.values(), key=lambda d:d['date'], reverse=True), recordings=[r for r in recordings if r['date']==date])


def make_handler(directory, pin):
    auth = Auth(pin)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(False)

        def do_HEAD(self):
            self.respond(True)

        def json_response(self, status, data, headers=None):
            payload = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            path = urlsplit(self.path).path
            origin = self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urlsplit(origin).netloc != self.headers.get('Host')):
                self.json_response(403, {'error': 'Origine refusée.'})
                return
            if path == '/api/logout':
                auth.logout(self.headers.get('Cookie'))
                self.json_response(200, {'ok': True}, {'Set-Cookie': f'{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
                return
            if path != '/api/login':
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 256:
                    raise ValueError
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(size))
                pin = data.get('pin') if isinstance(data, dict) else None
            except (ValueError, OSError):
                self.json_response(400, {'error': 'Requête invalide.'})
                return
            token, delay, blocked = auth.login(self.client_address[0], pin)
            if not token:
                self.json_response(429 if blocked else 401,
                                   {'error': 'Patientez avant de réessayer.' if blocked else 'Code incorrect.', 'retry_after': delay},
                                   {'Retry-After': str(delay)})
                return
            self.json_response(200, {'ok': True}, {'Set-Cookie': f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}'})

        def respond(self, head):
            parsed = urlsplit(self.path)
            public = parsed.path in ('/login', '/login.js', '/style.css')
            if not public and not auth.authenticated(self.headers.get('Cookie')):
                if parsed.path == '/':
                    self.send_response(303)
                    self.send_header('Location', '/login')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    self.send_error(401, 'Authentication required')
                return
            if parsed.path.startswith('/api/waveform/'):
                name = unquote(parsed.path[len('/api/waveform/'):])
                path = directory / 'recordings' / name
                if not AUDIO.fullmatch(name) or path.is_symlink():
                    self.send_error(404)
                    return
                try:
                    stat = path.stat()
                    data = recording_levels(path, stat.st_mtime_ns, stat.st_size)
                except (OSError, EOFError, wave.Error, ValueError):
                    self.send_error(404)
                    return
                if head:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                else:
                    self.json_response(200, data)
                return
            if parsed.path == '/api/dashboard':
                selected = parse_qs(parsed.query).get('date', [None])[0]
                if selected:
                    try:
                        if dt.date.fromisoformat(selected).isoformat() != selected:
                            raise ValueError
                    except ValueError:
                        self.send_error(400, 'Invalid date')
                        return
                try:
                    period = int(parse_qs(parsed.query).get('period', ['7'])[0])
                    if period not in (7, 30):
                        raise ValueError
                except ValueError:
                    self.send_error(400, 'Period must be 7 or 30 days')
                    return
                payload = json.dumps(dashboard_data(directory, selected, period)).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if not head:
                    self.wfile.write(payload)
                return
            if parsed.path in ('/', '/app.js', '/style.css', '/login', '/login.js'):
                name, content_type = {'/login':('login.html','text/html; charset=utf-8'), '/login.js':('login.js','text/javascript; charset=utf-8'), '/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'), '/style.css':('style.css','text/css; charset=utf-8')}[parsed.path]
                path = ROOT / 'web' / name
            elif parsed.path.startswith('/audio/'):
                name = unquote(parsed.path[len('/audio/'):])
                if not AUDIO.fullmatch(name):
                    self.send_error(404)
                    return
                path, content_type = directory / 'recordings' / name, 'audio/wav'
                if path.is_symlink():
                    self.send_error(404)
                    return
            else:
                self.send_error(404)
                return
            try:
                file = path.open('rb')
            except OSError:
                self.send_error(404)
                return
            with file:
                file.seek(0, 2)
                size = file.tell()
                start, end, status = 0, size-1, 200
                byte_range = self.headers.get('Range')
                if byte_range and content_type == 'audio/wav':
                    match = re.fullmatch(r'bytes=(\d*)-(\d*)', byte_range)
                    if not match or not any(match.groups()):
                        self.range_error(size)
                        return
                    if match[1]:
                        start = int(match[1])
                        end = min(int(match[2]), size-1) if match[2] else size-1
                    else:
                        start = max(0, size-int(match[2]))
                    if start > end or start >= size:
                        self.range_error(size)
                        return
                    status = 206
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(end-start+1))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-store')
                if content_type == 'audio/wav':
                    self.send_header('Accept-Ranges', 'bytes')
                if status == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                if not head:
                    file.seek(start)
                    remaining = end-start+1
                    try:
                        while remaining > 0:
                            block = file.read(min(65536, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        def range_error(self, size):
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0', help='Listening address (default: all LAN interfaces)')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR,
                        help='Data folder containing logs/ and recordings/ (default: project data/)')
    args = parser.parse_args()
    if args.data_dir == DATA_DIR:
        prepare_data_directory()
    if not args.data_dir.is_dir():
        parser.error('--data-dir must be an existing directory')
    try:
        pin = load_pin(ROOT / '.env')
    except ValueError as error:
        parser.error(str(error))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.data_dir.resolve(), pin))
    print(f'Dashboard: http://localhost:{args.port} — mobile: http://<IP locale de cette machine>:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
