import os

# Must be set before TensorFlow is imported
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"

import sounddevice as sd
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import datetime
import time
from collections import deque
import csv
from audio_recording import AudioBuffer, BarkRecorder
from storage import DATA_DIR, LOGS_DIR, RECORDINGS_DIR, prepare_data_directory
from detector_monitor import DetectorMonitor

# Constants
SAMPLE_RATE = 16000
CHUNK_DURATION = 1.2  # seconds
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
TOP_N_CLASSES = 5
BARK_CLASS_NAME = "Dog"
MIN_SESSION_DURATION = 0  # Log short sessions too
MIN_BARKS_PER_SESSION = 2
SESSION_GAP_SECONDS = 90
MIN_BARK_VOLUME = 0.012  # Filter out quiet barks (distant dogs)
RECORD_DURATION = 60  # Seconds of audio retained before the trigger
RECORD_QUIET_SECONDS = 10  # Keep recording until no detection for this long
CONSECUTIVE_BARKS = 2  # Consecutive positive 1.2-second chunks


def get_log_file_path():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"bark_log_{today}.txt"


def load_yamnet():
    print("Loading YAMNet model from TensorFlow Hub...")
    model = hub.load('https://tfhub.dev/google/yamnet/1')
    print("YAMNet model loaded.")
    return model


def load_class_map():
    class_map_path = os.path.join(os.path.dirname(__file__), 'yamnet_class_map.csv')
    with open(class_map_path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header
        return [row[2] for row in reader]


def log_header():
    now = datetime.datetime.now()
    header = (
        f"\n=== BARK LOGGER SESSION ===\n"
        f"DATE: {now:%Y-%m-%d}\n"
        f"START TIME: {now:%H:%M:%S}\n"
        f"===========================\n"
    )
    with open(get_log_file_path(), 'a') as f:
        f.write(header)


def log_bark(timestamp, volume):
    entry = f"[BARKING DETECTED] {timestamp:%Y-%m-%d %H:%M:%S} detected (volume: {volume:.4f})"
    print(entry)
    with open(get_log_file_path(), 'a', encoding='utf-8') as f:
        f.write(entry + '\n')


def log_session(start, end, count):
    # Subtract SESSION_GAP_SECONDS because the session end is detected only after
    # the gap has elapsed — the dog had already stopped barking by then.
    duration = max(0, (end - start).total_seconds() - SESSION_GAP_SECONDS)
    entry = f"[BARK SESSION] From {start:%Y-%m-%d %H:%M:%S} to {end:%Y-%m-%d %H:%M:%S} (Duration: {duration:.1f} seconds, {count} barks)"
    print(entry)
    with open(get_log_file_path(), 'a') as f:
        f.write(entry + '\n')


def run_detector(monitor):
    yamnet_model = load_yamnet()
    class_map = load_class_map()
    prepare_data_directory()
    audio_buffer = AudioBuffer(SAMPLE_RATE, CHUNK_SAMPLES, RECORD_DURATION)
    recorder = BarkRecorder(audio_buffer, RECORDINGS_DIR,
                            SAMPLE_RATE, CONSECUTIVE_BARKS, RECORD_QUIET_SECONDS)

    try:
        stream = sd.InputStream(callback=audio_buffer.callback, channels=1, samplerate=SAMPLE_RATE)
        stream.start()
        monitor.set_state('waiting_audio')
    except Exception as e:
        print(f"[ERROR] Failed to start audio stream: {e}")
        monitor.set_state('microphone_unavailable')
        raise

    recent_barks = deque()
    active_session = None
    current_bark_count = 0

    try:
        log_header()
        print("Listening for dog barks in real-time...")
        while True:
            monitor.heartbeat()
            now = datetime.datetime.now()
            chunk = audio_buffer.read_chunk()
            if chunk is None:
                recorder.poll(time.monotonic())
                time.sleep(0.05)
                continue

            scores, _, _ = yamnet_model(chunk)
            monitor.processed(audio_buffer.last_chunk_end, len(chunk) / SAMPLE_RATE)
            mean_scores = tf.reduce_mean(scores, axis=0).numpy()
            top_classes = [class_map[i] for i in mean_scores.argsort()[-TOP_N_CLASSES:][::-1]]
            bark_volume = np.mean(np.abs(chunk))

            is_bark = BARK_CLASS_NAME in top_classes and bark_volume >= MIN_BARK_VOLUME
            recorder.update(is_bark, time.monotonic(), now)

            if is_bark:
                log_bark(now, bark_volume)
                recent_barks.append(now)
                current_bark_count += 1

            while recent_barks and (now - recent_barks[0]).total_seconds() > SESSION_GAP_SECONDS:
                recent_barks.popleft()

            if recent_barks:
                if not active_session:
                    active_session = recent_barks[0]
                    current_bark_count = len(recent_barks)

            else:
                if active_session:
                    duration = (now - active_session).total_seconds() - SESSION_GAP_SECONDS
                    if duration >= MIN_SESSION_DURATION and current_bark_count >= MIN_BARKS_PER_SESSION:
                        log_session(active_session, now, current_bark_count)
                    else:
                        print(f"[SKIPPED SESSION] From {active_session} to {now} - below threshold")
                    active_session = None
                    current_bark_count = 0

    except KeyboardInterrupt:
        print("Stopped. Analyzing bark sessions...")
        now = datetime.datetime.now()
        if active_session:
            duration = (now - active_session).total_seconds() - SESSION_GAP_SECONDS
            if duration >= MIN_SESSION_DURATION and current_bark_count >= MIN_BARKS_PER_SESSION:
                log_session(active_session, now, current_bark_count)
            else:
                print(f"[SKIPPED SESSION] From {active_session} to {now} - below threshold")
    finally:
        try:
            stream.stop()
        finally:
            try:
                recorder.finish()
            finally:
                stream.close()


def main():
    monitor = DetectorMonitor(DATA_DIR)
    try:
        run_detector(monitor)
    except KeyboardInterrupt:
        monitor.set_state('stopped')
    except Exception:
        if monitor.state != 'microphone_unavailable':
            monitor.set_state('error')
        raise
    else:
        monitor.set_state('stopped')
    finally:
        monitor.close()


if __name__ == '__main__':
    main()
