"""Compatibility import for the music service."""
from app.services.music import BarkMusic, load_music_config, play_track, ensure_speaker, log_music_event

if __name__ == '__main__':
    import sys
    from pathlib import Path
    if len(sys.argv) == 4 and sys.argv[1] == '--play':
        raise SystemExit(play_track(Path(sys.argv[3]), int(sys.argv[2]), event=log_music_event, prepare=ensure_speaker))
    raise SystemExit('Use python -m app.music_player --help')
