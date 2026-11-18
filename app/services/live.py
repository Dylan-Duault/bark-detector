"""One authenticated, half-duplex WebRTC session."""
import asyncio
import contextlib
from datetime import datetime
import fcntl
from fractions import Fraction
from functools import partial
import json
import logging
import os
import re
import socket
import subprocess
import time
from urllib.request import Request, urlopen

from aiortc import AudioStreamTrack, RTCConfiguration, RTCIceServer, RTCPeerConnection
from av import AudioFrame, AudioResampler
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.live_audio import mic_socket, voice_lock
from app.services.music import ensure_speaker

logger = logging.getLogger(__name__)

SESSION_SECONDS = 600
RATE = 16000
FRAME_BYTES = RATE // 50 * 2
VOICE_FRAME_BYTES = 48000 // 50 * 2
PLAYER_NODE = 'bark-direct-playback'


def ice_servers(settings):
    key = settings.live_turn_key.get_secret_value()
    if not settings.live_turn_key_id and not key:
        return []
    if not settings.live_turn_key_id or not key:
        raise ValueError('Configuration TURN incomplète')
    request = Request(
        f'https://rtc.live.cloudflare.com/v1/turn/keys/{settings.live_turn_key_id}/credentials/generate-ice-servers',
        data=json.dumps({'ttl': 900}).encode(),
        headers={'Authorization': f'Bearer {key}',
                 'Content-Type': 'application/json',
                 'User-Agent': 'bark-detector'},
    )
    with urlopen(request, timeout=6) as response:
        servers = json.load(response)['iceServers']
    for server in servers:
        # Cloudflare's alternate port 53 is blocked by browsers.
        server['urls'] = [url for url in server['urls'] if not re.search(r':53(?:\?|$)', url)]
    return servers


def player_linked(env, target):
    result = subprocess.run(['pw-dump'], env=env, check=True, capture_output=True, timeout=2)
    graph = json.loads(result.stdout)
    nodes = {node.get('info', {}).get('props', {}).get('node.name'): node['id']
             for node in graph if node['type'] == 'PipeWire:Interface:Node'}
    player, speaker = nodes.get(PLAYER_NODE), nodes.get(target)
    return player is not None and speaker is not None and any(
        item['type'] == 'PipeWire:Interface:Link'
        and item['info']['output-node-id'] == player
        and item['info']['input-node-id'] == speaker
        and item['info']['state'] == 'active'
        for item in graph
    )


class HouseMicrophone(AudioStreamTrack):
    def __init__(self, address, muted):
        super().__init__()
        self.address = address
        self.muted = muted
        self.payload = bytes(FRAME_BYTES)
        self.last_packet = 0
        self.pts = 0
        self.next_frame = 0
        self.loop = asyncio.get_running_loop()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.socket.setblocking(False)
            address.unlink(missing_ok=True)
            self.socket.bind(str(address))
            address.chmod(0o600)
            self.loop.add_reader(self.socket, self.read)
        except BaseException:
            self.socket.close()
            raise

    def read(self):
        with contextlib.suppress(BlockingIOError):
            for _ in range(16):
                payload = self.socket.recv(FRAME_BYTES + 1)
                if len(payload) == FRAME_BYTES:
                    self.payload = payload
                    self.last_packet = self.loop.time()

    async def recv(self):
        now = self.loop.time()
        self.next_frame = max(now, self.next_frame + .02)
        await asyncio.sleep(self.next_frame - now)
        active = not self.muted() and self.loop.time() - self.last_packet < .05
        frame = AudioFrame(format='s16', layout='mono', samples=RATE // 50)
        frame.planes[0].update(self.payload if active else bytes(FRAME_BYTES))
        frame.pts = self.pts
        frame.sample_rate = RATE
        frame.time_base = Fraction(1, RATE)
        self.pts += RATE // 50
        return frame

    def stop(self):
        if self.readyState == 'live':
            self.loop.remove_reader(self.socket)
            self.socket.close()
            self.address.unlink(missing_ok=True)
        super().stop()


class LiveSession:
    def __init__(self, settings, authenticated, ice, record_voice):
        self.settings = settings
        self.authenticated = authenticated
        self.record_voice = record_voice
        self.voice_logged = False
        self.started = time.monotonic()
        self.press_until = 0
        self.last_ping = self.started
        self.echo_until = 0
        self.monitor_voice = False
        self.process = None
        self.lock = None
        self.tasks = set()
        self.closed = asyncio.Event()
        self.voice = bytearray()
        self.speaker_task = None
        self.speaker_ready = False
        self.audio_env = os.environ.copy()
        self.audio_env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        self.channel = None
        self.last_mic_state = None
        # Let aiortc bundle after reading the offer. Sharing the ICE transport
        # up front can overwrite audio candidates with an empty data section.
        self.pc = RTCPeerConnection(RTCConfiguration(
            iceServers=[RTCIceServer(**server) for server in ice],
        ))
        self.microphone = HouseMicrophone(mic_socket(settings.data_dir), self.muted)
        self.pc.addTrack(self.microphone)
        self.pc.on('track', lambda track: self.spawn(self.receive(track)))
        self.pc.on('datachannel', self.control)

    def muted(self):
        now = time.monotonic()
        return not self.monitor_voice and (self.press_until > now or self.echo_until > now)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def send(self, message):
        if self.channel is not None and self.channel.readyState == 'open':
            self.channel.send(message)

    def control(self, channel):
        if channel.label != 'direct' or self.channel is not None:
            channel.close()
            return
        self.channel = channel
        channel.on('message', self.command)
        channel.on('close', self.closed.set)

    def command(self, message):
        if message == 'ping':
            self.last_ping = time.monotonic()
        elif message in ('monitor-on', 'monitor-off'):
            self.monitor_voice = message == 'monitor-on'
        elif message == 'prepare-speaker':
            if self.speaker_ready:
                self.send('speaker-ready')
            elif self.speaker_task is None:
                self.speaker_task = asyncio.create_task(self.prepare_speaker())
        elif message == 'close':
            self.closed.set()
        elif message == 'release':
            self.release()
        elif message == 'hold' and self.press_until:
            self.press_until = time.monotonic() + 1.5
        elif message == 'press' and self.speaker_ready and not self.press_until:
            try:
                self.lock = voice_lock(self.settings.data_dir)
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.speaker_failed()
                return
            self.press_until = time.monotonic() + 1.5
            self.voice_logged = False
            self.send('talking')

    async def prepare_speaker(self):
        self.send('speaker-connecting')
        try:
            target = await asyncio.to_thread(
                ensure_speaker, run=partial(subprocess.run, env=self.audio_env),
                address=self.settings.bark_speaker_address, select_default=False,
            )
            if self.closed.is_set():
                return
            process = await asyncio.create_subprocess_exec(
                'pw-cat', '--playback', '--raw', '--target', target, '--media-role', 'Communication',
                '--properties', json.dumps({'node.name': PLAYER_NODE, 'node.dont-fallback': True,
                                            'node.dont-reconnect': True}),
                '--format', 's16', '--channels', '1', '--rate', '48000', '--latency', '60ms',
                '--volume', str(self.settings.live_voice_volume_percent / 100), '-',
                stdin=asyncio.subprocess.PIPE, env=self.audio_env,
            )
            if self.closed.is_set():
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
                return
            process.stdin.transport.set_write_buffer_limits(high=VOICE_FRAME_BYTES, low=0)
            self.process = process
            self.spawn(self.play_voice(process))
            for _ in range(12):
                linked = await asyncio.to_thread(player_linked, self.audio_env, target)
                if self.process is not process:
                    return
                if linked:
                    self.speaker_ready = True
                    self.send('speaker-ready')
                    return
                await asyncio.sleep(.2)
            raise OSError('Le lecteur n’est pas relié à la sortie Bluetooth.')
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            logger.warning('Enceinte du direct indisponible (%s)', error)
            self.speaker_failed()
        finally:
            self.speaker_task = None

    def release(self):
        if self.press_until:
            self.echo_until = time.monotonic() + .3
        self.press_until = 0
        self.voice.clear()
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def stop_player(self):
        process, self.process = self.process, None
        self.speaker_ready = False
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        return process

    def speaker_failed(self):
        self.release()
        self.stop_player()
        self.send('speaker-error')

    async def play_voice(self, process):
        # Keep the Bluetooth sink warm and send silence between presses.
        # Limit queued speech to two frames so delayed packets cannot accumulate.
        try:
            loop = asyncio.get_running_loop()
            next_frame = loop.time()
            while self.process is process:
                if process.returncode is not None:
                    raise BrokenPipeError()
                if self.press_until > time.monotonic():
                    frame = bytes(self.voice[:VOICE_FRAME_BYTES])
                    del self.voice[:VOICE_FRAME_BYTES]
                else:
                    frame = b''
                process.stdin.write(frame.ljust(VOICE_FRAME_BYTES, b'\0'))
                if not self.voice_logged and frame.strip(b'\0'):
                    self.voice_logged = True
                    self.send('voice-sent')
                    self.spawn(self.log_voice(datetime.now()))
                await asyncio.wait_for(process.stdin.drain(), timeout=.2)
                next_frame = max(next_frame + .02, loop.time())
                await asyncio.sleep(next_frame - loop.time())
        except (TimeoutError, OSError) as error:
            if self.process is process:
                logger.warning('Lecture du direct interrompue (%s)', type(error).__name__)
                self.speaker_failed()

    async def log_voice(self, timestamp):
        try:
            await asyncio.to_thread(self.record_voice, timestamp)
        except SQLAlchemyError:
            logger.exception('Impossible de journaliser la prise de parole')

    async def receive(self, track):
        if track.kind != 'audio':
            return
        from aiortc.mediastreams import MediaStreamError

        resampler = AudioResampler(format='s16', layout='mono', rate=48000)
        try:
            while True:
                frame = await track.recv()
                if self.press_until > time.monotonic():
                    for pcm in resampler.resample(frame):
                        self.voice.extend(bytes(pcm.planes[0])[:pcm.samples * 2])
                    if len(self.voice) > 2 * VOICE_FRAME_BYTES:
                        del self.voice[:-2 * VOICE_FRAME_BYTES]
        except MediaStreamError:
            self.release()

    async def watch(self):
        try:
            while not self.closed.is_set():
                now = time.monotonic()
                state = self.pc.connectionState
                if (state in ('failed', 'closed') or not self.authenticated()
                        or now - self.started > (SESSION_SECONDS if state == 'connected' else 30)
                        or (self.channel is not None and now - self.last_ping > 12)):
                    return
                if self.press_until and self.press_until < now:
                    self.release()
                mic_state = 'mic-ready' if self.microphone.loop.time() - self.microphone.last_packet < 2 else 'mic-missing'
                if self.channel is not None and self.channel.readyState == 'open' and mic_state != self.last_mic_state:
                    self.send(mic_state)
                    self.last_mic_state = mic_state
                await asyncio.sleep(.25)
        finally:
            await self.close()

    async def close(self):
        self.closed.set()
        self.release()
        process = self.stop_player()
        try:
            await self.pc.close()
        finally:
            self.microphone.stop()
            tasks = tuple(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if process is not None:
                await process.wait()
