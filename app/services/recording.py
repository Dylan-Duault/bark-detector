"""Microphone buffering and recordings spanning complete barking sequences."""
from collections import deque
import os
from pathlib import Path
from threading import Lock
import time

import numpy as np
import soundfile as sf


class AudioBuffer:
    def __init__(self, sample_rate=16000, chunk_samples=19200, history_seconds=60):
        self.chunk_samples = chunk_samples
        self.history_samples = int(sample_rate * history_seconds)
        self.buffer = deque(maxlen=chunk_samples)
        self.history = deque()
        self.history_length = 0
        self.pending = []
        self.capturing = False
        self.lock = Lock()
        self.last_input_at = None
        self.last_input_tick = None
        self.last_chunk_end = None

    def callback(self, indata, frames, time_info, status):
        if status:
            print(f"[WARNING] InputStream status: {status}")
        mono = indata[:, 0].copy()
        with self.lock:
            self.last_input_at = time.time()
            self.last_input_tick = time.monotonic()
            self.buffer.extend(mono)
            self.history.append(mono)
            self.history_length += len(mono)
            while self.history_length > self.history_samples:
                excess = self.history_length - self.history_samples
                if len(self.history[0]) <= excess:
                    self.history_length -= len(self.history.popleft())
                else:
                    self.history[0] = self.history[0][excess:]
                    self.history_length -= excess
            if self.capturing:
                self.pending.append(mono)

    def read_chunk(self):
        with self.lock:
            if len(self.buffer) < self.chunk_samples:
                return None
            self.last_chunk_end = self.last_input_at
            return np.array([self.buffer.popleft() for _ in range(self.chunk_samples)], dtype=np.float32)

    def start_capture(self):
        with self.lock:
            self.capturing = True
            self.pending = []
            return list(self.history)

    def drain_capture(self, stop=False):
        with self.lock:
            blocks, self.pending = self.pending, []
            if stop:
                self.capturing = False
            return blocks


class BarkRecorder:
    def __init__(self, audio_buffer, directory, sample_rate=16000, consecutive=2, quiet_seconds=10, on_saved=None):
        self.buffer = audio_buffer
        self.on_saved = on_saved
        self.directory = Path(directory)
        self.sample_rate = sample_rate
        self.required = consecutive
        self.quiet_seconds = quiet_seconds
        self.consecutive = 0
        self.last_bark = None
        self.writer = None
        self.path = None
        self.partial = None

    def update(self, is_bark, now, timestamp):
        """Use a monotonic clock for quiet gaps, wall time only for filenames."""
        self.consecutive = self.consecutive + 1 if is_bark else 0
        if is_bark:
            self.last_bark = now
        if self.writer is None and self.consecutive >= self.required:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.path = self.directory / f'bark_audio_{timestamp:%Y-%m-%d_%H-%M-%S}.wav'
            self.partial = self.path.with_suffix('.wav.part')
            self.writer = sf.SoundFile(str(self.partial), mode='w', samplerate=self.sample_rate,
                                       channels=1, subtype='PCM_16', format='WAV')
            for block in self.buffer.start_capture():
                self.writer.write(block)
            print(f'[WAV] Recording started: {self.path.name}')
        self.poll(now)

    def poll(self, now):
        if self.writer is None:
            return
        if now - self.last_bark >= self.quiet_seconds:
            self.finish()
        else:
            for block in self.buffer.drain_capture():
                self.writer.write(block)

    def finish(self):
        """Flush on a quiet gap or clean shutdown; publish only a complete WAV."""
        if self.writer is None:
            return
        writer, self.writer = self.writer, None
        try:
            for block in self.buffer.drain_capture(stop=True):
                writer.write(block)
        finally:
            writer.close()
        os.replace(self.partial, self.path)
        self.consecutive = 0
        if self.on_saved:
            self.on_saved(self.path)
        print(f'[WAV] Saved recording: {self.path.name}')
