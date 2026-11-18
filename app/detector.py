"""Independent detector entry point; the web process never opens the microphone."""
import datetime as dt
import fcntl
import signal
import time

from app.config import Settings
from app.infrastructure.database import Database
from app.services.history import History
from app.infrastructure.live_audio import MicrophoneFeed
from app.services.migration import initialize
from app.services.monitoring import DetectorMonitor
from app.services.music import BarkMusic
from app.services.recordings import index_recording
from app.services.sessions import SessionTracker


def run(settings, database, monitor):
    import sounddevice as sd
    from app.infrastructure.yamnet import Yamnet
    from app.services.recording import AudioBuffer, BarkRecorder

    history = History(database)
    tracker = SessionTracker(history, settings.session_gap_seconds,
                             settings.min_barks_per_session, settings.min_session_duration)
    music = BarkMusic(**settings.music_options)
    stream = recorder = feed = None
    try:
        model = Yamnet(settings)
        buffer = AudioBuffer(settings.sample_rate, int(settings.sample_rate * settings.chunk_duration), settings.record_duration)
        recorder = BarkRecorder(buffer, settings.data_dir / 'recordings', settings.sample_rate,
                                settings.consecutive_barks, settings.record_quiet_seconds,
                                on_saved=lambda path: index_recording(database, path))
        try:
            callback = buffer.callback
            options = {}
            if settings.live_audio_enabled:
                feed = MicrophoneFeed(settings.data_dir)
                options['blocksize'] = settings.sample_rate // 50

                def callback(indata, frames, time_info, status):
                    buffer.callback(indata, frames, time_info, status)
                    feed.publish((indata[:, 0].clip(-1, 1) * 32767).astype('<i2'))

            stream = sd.InputStream(callback=callback, channels=1, samplerate=settings.sample_rate, **options)
            stream.start()
        except Exception:
            monitor.set_state('microphone_unavailable')
            raise
        monitor.set_state('waiting_audio')
        print('Listening for dog vocalisations…', flush=True)
        while True:
            monitor.heartbeat()
            speaking = feed is not None and feed.speaking()
            if speaking:
                music.yield_to_voice()
            chunk = buffer.read_chunk()
            if chunk is None:
                if not stream.active:
                    monitor.set_state('microphone_unavailable')
                    raise RuntimeError('Microphone stream stopped unexpectedly')
                tick = time.monotonic()
                recorder.poll(tick)
                tracker.update(False, dt.datetime.now(), tick)
                time.sleep(.05)
                continue
            is_bark, volume = model.classify(chunk)
            now, tick = dt.datetime.now(), time.monotonic()
            monitor.processed(buffer.last_chunk_end, len(chunk) / settings.sample_rate)
            recorder.update(is_bark, tick, now)
            tracker.update(is_bark, now, tick)
            if is_bark:
                history.detection(now, volume)
                print(f'[BARKING DETECTED] {now.isoformat()} volume={volume:.4f}', flush=True)
                if not speaking:
                    music.detected()
    finally:
        try:
            tracker.finish()
        finally:
            music.close()
            try:
                if stream:
                    stream.stop()
            finally:
                try:
                    if recorder:
                        recorder.finish()
                finally:
                    try:
                        if stream:
                            stream.close()
                    finally:
                        if feed:
                            feed.close()


def main(settings=None):
    settings = settings or Settings()
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    database = Database(settings.data_dir)
    monitor = None
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    lock = (settings.data_dir / '.detector.lock').open('a')
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A detector is already running for this data directory') from None
        initialize(database)
        monitor = DetectorMonitor(settings.data_dir, database=database)
        run(settings, database, monitor)
    except KeyboardInterrupt:
        if monitor:
            monitor.set_state('stopped')
    except Exception:
        if monitor and monitor.state != 'microphone_unavailable':
            monitor.set_state('error')
        raise
    finally:
        try:
            if monitor:
                monitor.close()
        finally:
            database.close()
            lock.close()


if __name__ == '__main__':
    main()
