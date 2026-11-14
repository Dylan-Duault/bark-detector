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
    return os.path.join(os.path.dirname(__file__), f"bark_log_{today}.txt")


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


def format_duration(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    elif seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def log_summary(total_duration, total_barks):
    end_time = datetime.datetime.now()
    formatted = format_duration(total_duration)
    entry = f"[SUMMARY] Session ended at {end_time:%Y-%m-%d %H:%M:%S} | Total barking time: {formatted} | Total barks: {total_barks}"
    print(entry)
    with open(get_log_file_path(), 'a') as f:
        f.write(entry + '\n')


def main():
    yamnet_model = load_yamnet()
    class_map = load_class_map()
    audio_buffer = AudioBuffer(SAMPLE_RATE, CHUNK_SAMPLES, RECORD_DURATION)
    recorder = BarkRecorder(audio_buffer, os.path.join(os.path.dirname(__file__), "recordings"),
                            SAMPLE_RATE, CONSECUTIVE_BARKS, RECORD_QUIET_SECONDS)

    log_header()
    print("Listening for dog barks in real-time...")

    try:
        stream = sd.InputStream(callback=audio_buffer.callback, channels=1, samplerate=SAMPLE_RATE)
        stream.start()
    except Exception as e:
        print(f"[ERROR] Failed to start audio stream: {e}")
        return

    recent_barks = deque()
    active_session = None
    total_bark_duration = 0
    current_bark_count = 0
    total_barks = 0

    try:
        while True:
            now = datetime.datetime.now()
            chunk = audio_buffer.read_chunk()
            if chunk is None:
                recorder.poll(time.monotonic())
                time.sleep(0.05)
                continue

            scores, _, _ = yamnet_model(chunk)
            mean_scores = tf.reduce_mean(scores, axis=0).numpy()
            top_classes = [class_map[i] for i in mean_scores.argsort()[-TOP_N_CLASSES:][::-1]]
            bark_volume = np.mean(np.abs(chunk))

            is_bark = BARK_CLASS_NAME in top_classes and bark_volume >= MIN_BARK_VOLUME
            recorder.update(is_bark, time.monotonic(), now)

            if is_bark:
                log_bark(now, bark_volume)
                recent_barks.append(now)
                current_bark_count += 1
                total_barks += 1

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
                        total_bark_duration += duration
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
                total_bark_duration += duration
            else:
                print(f"[SKIPPED SESSION] From {active_session} to {now} - below threshold")
        log_summary(total_bark_duration, total_barks)
    finally:
        try:
            stream.stop()
        finally:
            try:
                recorder.finish()
            finally:
                stream.close()


if __name__ == '__main__':
    main()
