"""Short-lived playback process; Bluetooth and volume checks stay off the detector."""
import argparse
from functools import partial
from pathlib import Path
from app.services.music import ensure_speaker, log_music_event, play_track


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--volume', type=int, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--speaker', required=True)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    if not 0 <= args.volume <= 100:
        parser.error('Volume must be between 0 and 100')
    return play_track(args.path, args.volume,
                      event=partial(log_music_event, directory=args.data_dir),
                      prepare=partial(ensure_speaker, address=args.speaker))


if __name__ == '__main__':
    raise SystemExit(main())
