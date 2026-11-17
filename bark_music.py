"""Optional, non-blocking music playback after a burst of bark detections."""
from collections import deque
import os
import datetime as dt
import json
from storage import LOGS_DIR
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def load_music_config(path):
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        lines = []
    values = {}
    for line in lines:
        key, separator, setting = line.strip().partition('=')
        if separator and not key.startswith('#'):
            values[key.strip()] = setting.strip().strip('\"\'')
    value = values.get('BARK_MUSIC_ENABLED', 'false').lower()
    if value not in ('true', 'false', '1', '0', 'yes', 'no', 'on', 'off'):
        raise ValueError('BARK_MUSIC_ENABLED must be true or false')
    config = {'enabled': value in ('true', '1', 'yes', 'on')}
    for key, argument, default in (
            ('BARK_MUSIC_BARK_COUNT', 'bark_count', 20),
            ('BARK_MUSIC_WINDOW_SECONDS', 'window_seconds', 300)):
        try:
            number = int(values.get(key, str(default)))
            if number <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f'{key} must be a positive integer') from None
        config[argument] = number
    try:
        volume = int(values.get('BARK_MUSIC_VOLUME_PERCENT', '35'))
        if not 0 <= volume <= 100:
            raise ValueError
    except ValueError:
        raise ValueError('BARK_MUSIC_VOLUME_PERCENT must be an integer from 0 to 100') from None
    config['volume_percent'] = volume
    return config


def log_music_event(status, track, detail='', directory=LOGS_DIR):
    now = dt.datetime.now()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / f'music_{now:%Y-%m-%d}.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(dict(time=now.strftime('%H:%M:%S'), track=Path(track).name,
                                      status=status, detail=detail), ensure_ascii=False) + '\n')
    except OSError as error:
        print(f'[MUSIC] Unable to save event: {error}', flush=True)


ACTON_ADDRESS = '74:68:59:AA:5E:05'


def ensure_speaker(run=subprocess.run, sleep=time.sleep):
    """Reconnect the paired speaker and wait for its real PipeWire audio node."""
    info = run(['bluetoothctl', 'info', ACTON_ADDRESS], check=True, timeout=10,
               capture_output=True, text=True)
    if 'Connected: yes' not in info.stdout:
        print('[MUSIC] Reconnecting ACTON III', flush=True)
        run(['bluetoothctl', 'connect', ACTON_ADDRESS], check=True, timeout=25,
            capture_output=True, text=True)
    for attempt in range(10):
        result = run(['pw-dump'], check=True, timeout=5, capture_output=True, text=True)
        for item in json.loads(result.stdout):
            props = item.get('info', {}).get('props', {})
            name = props.get('node.name', '')
            if (props.get('media.class') == 'Audio/Sink'
                    and ACTON_ADDRESS.replace(':', '_') in name):
                run(['wpctl', 'set-default', str(item['id'])], check=True, timeout=5)
                return
        if attempt < 9:
            sleep(1)
    raise OSError('ACTON III : aucune sortie audio disponible après reconnexion Bluetooth.')


def play_track(path, volume_percent, run=subprocess.run, sleep=time.sleep, execute=os.execvp,
               event=None, prepare=None):
    """Run in a child process so volume checks never block microphone analysis."""
    detail = ''
    try:
        if prepare:
            prepare()
        for _ in range(3):
            run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{volume_percent}%'],
                check=True, timeout=5)
            run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0'], check=True, timeout=5)
            sleep(.5)  # Allow Bluetooth volume synchronization to settle.
            result = run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'],
                         check=True, timeout=5, capture_output=True, text=True)
            parts = result.stdout.split()
            if len(parts) >= 2 and parts[0] == 'Volume:' and '[MUTED]' not in parts:
                if abs(float(parts[1]) - volume_percent / 100) <= .01:
                    print(f'[MUSIC] Volume verified: {volume_percent}%', flush=True)
                    # Replace this helper so stopping the detector also stops the player.
                    if event:
                        event('started', path)
                    execute('ffplay', ['ffplay', '-nodisp', '-autoexit', '-loglevel',
                                       'error', str(path)])
                    return 0
        detail = f'Volume non vérifié à {volume_percent}% après trois tentatives.'
        print(f'[MUSIC] Playback cancelled: volume could not be verified at {volume_percent}%',
              flush=True)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        detail = str(error)
        print(f'[MUSIC] Playback failed: {error}', flush=True)
    if event:
        event('failed', path, detail)
    return 1


class BarkMusic:
    def __init__(self, enabled=False, path=ROOT / 'data/music',
                 clock=time.monotonic, spawn=subprocess.Popen,
                 bark_count=20, window_seconds=300, volume_percent=35):
        self.enabled = enabled
        self.path = Path(path)
        self.clock = clock
        self.spawn = spawn
        self.bark_count = bark_count
        self.window_seconds = window_seconds
        self.volume_percent = volume_percent
        self.barks = deque(maxlen=bark_count)
        self.process = None
        self.retry_at = 0
        self.last_track = None
        if self.path.is_dir():
            try:
                self.last_track = (self.path / '.last-track').read_text().strip()
            except OSError:
                pass

    def next_track(self):
        tracks = sorted(self.path.glob('*.mp3')) if self.path.is_dir() else [self.path]
        tracks = [track for track in tracks if track.is_file()]
        if not tracks:
            raise FileNotFoundError(f'No MP3 files in {self.path}')
        names = [track.name for track in tracks]
        index = (names.index(self.last_track) + 1) % len(tracks) if self.last_track in names else 0
        return tracks[index]

    def detected(self):
        if not self.enabled:
            return
        now = self.clock()
        if self.process is not None:
            if self.process.poll() is None:
                return
            if self.process.returncode:
                print(f'[MUSIC] Player exited with code {self.process.returncode}', flush=True)
            self.process = None
            self.barks.clear()
        while self.barks and now - self.barks[0] >= self.window_seconds:
            self.barks.popleft()
        self.barks.append(now)
        if len(self.barks) < self.bark_count or now < self.retry_at:
            return
        # The system service uses the same user's PipeWire/PulseAudio session.
        env = os.environ.copy()
        env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        env['SDL_AUDIODRIVER'] = 'pulseaudio'
        try:
            track = self.next_track()
            self.process = self.spawn(
                [sys.executable, str(Path(__file__).resolve()), '--play',
                 str(self.volume_percent), str(track)], env=env, stdin=subprocess.DEVNULL)
        except OSError as error:
            print(f'[MUSIC] Unable to start playback: {error}', flush=True)
            log_music_event('failed', self.path, str(error))
            self.retry_at = now + 60
        else:
            self.last_track = track.name
            if self.path.is_dir():
                try:
                    temporary = self.path / '.last-track.tmp'
                    temporary.write_text(track.name + '\n')
                    temporary.replace(self.path / '.last-track')
                except OSError as error:
                    print(f'[MUSIC] Unable to save playlist position: {error}', flush=True)
            self.barks.clear()
            print(f'[MUSIC] {self.bark_count} detections in less than '
                  f'{self.window_seconds} seconds: playing {track.name}', flush=True)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--play':
        raise SystemExit(play_track(Path(sys.argv[3]), int(sys.argv[2]), event=log_music_event, prepare=ensure_speaker))
    raise SystemExit('Usage: bark_music.py --play VOLUME_PERCENT PATH')
