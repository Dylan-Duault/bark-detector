from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import Mock, patch

from bark_music import BarkMusic, load_music_config, play_track, ensure_speaker


class MusicTests(unittest.TestCase):
    def setUp(self):
        logger = patch('bark_music.log_music_event')
        logger.start()
        self.addCleanup(logger.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'music.mp3'
        self.path.touch()
        self.now = 0
        self.process = Mock(returncode=0)
        self.process.poll.return_value = None
        self.spawn = Mock(return_value=self.process)
        self.music = BarkMusic(True, self.path, lambda: self.now, self.spawn)

    def detect(self, count):
        for _ in range(count):
            self.music.detected()
            self.now += 1

    def test_starts_at_twentieth_detection_and_never_overlaps(self):
        self.detect(19)
        self.spawn.assert_not_called()
        self.detect(1)
        self.spawn.assert_called_once()
        self.detect(50)
        self.spawn.assert_called_once()
        self.process.poll.return_value = 0
        self.detect(19)
        self.spawn.assert_called_once()
        self.detect(1)
        self.assertEqual(self.spawn.call_count, 2)

    def test_window_is_strictly_less_than_five_minutes(self):
        self.music.detected()
        self.now = 282
        self.detect(19)  # The twentieth detection is exactly 300 seconds later.
        self.spawn.assert_not_called()
        self.detect(1)
        self.spawn.assert_called_once()

    def test_disabled_does_not_play(self):
        self.music.enabled = False
        self.detect(30)
        self.spawn.assert_not_called()

    def test_player_failure_does_not_interrupt_detector_and_retries_are_throttled(self):
        self.spawn.side_effect = FileNotFoundError('ffplay')
        self.detect(30)
        self.spawn.assert_called_once()
        self.now = 80
        self.music.detected()
        self.assertEqual(self.spawn.call_count, 2)

    def test_close_stops_playback(self):
        self.detect(20)
        self.music.close()
        self.process.terminate.assert_called_once()
        self.process.wait.assert_called_once_with(timeout=5)

    def test_config_defaults_to_disabled_and_accepts_boolean(self):
        config = self.path.parent / '.env'
        self.assertEqual(load_music_config(config),
                         dict(enabled=False, bark_count=20, window_seconds=300, volume_percent=35))
        config.write_text('DASHBOARD_PIN=1234\nBARK_MUSIC_ENABLED=true\n')
        self.assertTrue(load_music_config(config)['enabled'])
        config.write_text('BARK_MUSIC_ENABLED=false\n')
        self.assertFalse(load_music_config(config)['enabled'])
        config.write_text('BARK_MUSIC_ENABLED=typo\n')
        with self.assertRaises(ValueError):
            load_music_config(config)

    def test_custom_threshold_and_period(self):
        config = self.path.parent / '.env'
        config.write_text('BARK_MUSIC_ENABLED=true\nBARK_MUSIC_BARK_COUNT=3\n'
                          'BARK_MUSIC_WINDOW_SECONDS=10\n')
        self.music = BarkMusic(path=self.path, clock=lambda: self.now,
                               spawn=self.spawn, **load_music_config(config))
        self.detect(2)
        self.now = 10  # The first detection has expired.
        self.detect(1)
        self.spawn.assert_not_called()
        self.detect(1)  # The second detection also expires at exactly 10 seconds.
        self.spawn.assert_not_called()
        self.detect(1)
        self.spawn.assert_called_once()

    def test_invalid_thresholds_are_rejected(self):
        config = self.path.parent / '.env'
        for key in ('BARK_MUSIC_BARK_COUNT', 'BARK_MUSIC_WINDOW_SECONDS'):
            for value in ('0', '-1', '1.5', 'abc', ''):
                with self.subTest(key=key, value=value):
                    config.write_text(f'{key}={value}\n')
                    with self.assertRaisesRegex(ValueError, key):
                        load_music_config(config)

    def test_playlist_rotates_wraps_and_resumes_after_restart(self):
        directory = self.path.parent
        (directory / 'another.mp3').touch()
        music = BarkMusic(True, directory, lambda: self.now, self.spawn, bark_count=1)
        music.detected()
        self.assertEqual(Path(self.spawn.call_args.args[0][-1]).name, 'another.mp3')
        music.detected()  # Still playing: no overlap or advancement.
        self.spawn.assert_called_once()
        self.process.poll.return_value = 0
        music.detected()
        self.assertEqual(Path(self.spawn.call_args.args[0][-1]).name, 'music.mp3')
        music = BarkMusic(True, directory, lambda: self.now, self.spawn, bark_count=1)
        music.detected()
        self.assertEqual(Path(self.spawn.call_args.args[0][-1]).name, 'another.mp3')

    def test_empty_playlist_and_missing_player_do_not_advance_position(self):
        self.path.unlink()
        directory = self.path.parent
        music = BarkMusic(True, directory, lambda: self.now, self.spawn, bark_count=1)
        music.detected()
        self.spawn.assert_not_called()
        self.path.touch()
        self.now = 61
        self.spawn.side_effect = FileNotFoundError('ffplay')
        music.detected()
        self.assertFalse((directory / '.last-track').exists())

    def test_deleted_last_track_does_not_break_rotation(self):
        directory = self.path.parent
        (directory / '.last-track').write_text('deleted.mp3\n')
        music = BarkMusic(True, directory, lambda: self.now, self.spawn, bark_count=1)
        music.detected()
        self.assertEqual(Path(self.spawn.call_args.args[0][-1]), self.path)

    def test_volume_is_verified_before_player_starts(self):
        run = Mock(return_value=Mock(stdout='Volume: 0.35\n', returncode=0))
        execute = Mock()
        self.assertEqual(play_track(self.path, 35, run, Mock(), execute), 0)
        execute.assert_called_once()
        self.assertEqual([call.args[0][0:2] for call in run.call_args_list],
                         [['wpctl', 'set-volume'], ['wpctl', 'set-mute'],
                          ['wpctl', 'get-volume']])

    def test_wrong_or_muted_volume_prevents_playback(self):
        for output in ('Volume: 0.20', 'Volume: 0.35 [MUTED]'):
            run = Mock(return_value=Mock(stdout=output))
            self.assertEqual(play_track(self.path, 35, run, Mock()), 1)
            self.assertFalse(any(call.args[0][0] == 'ffplay' for call in run.call_args_list))

    def test_volume_configuration_bounds(self):
        config = self.path.parent / '.env'
        for value in ('-1', '101', '35.5', 'abc', ''):
            config.write_text(f'BARK_MUSIC_VOLUME_PERCENT={value}\n')
            with self.assertRaisesRegex(ValueError, 'BARK_MUSIC_VOLUME_PERCENT'):
                load_music_config(config)
        config.write_text('BARK_MUSIC_VOLUME_PERCENT=42\n')
        self.assertEqual(load_music_config(config)['volume_percent'], 42)

    def test_playback_events_report_verified_start_and_failure(self):
        event = Mock()
        run = Mock(return_value=Mock(stdout='Volume: 0.35'))
        play_track(self.path, 35, run, Mock(), Mock(), event=event)
        event.assert_called_once_with('started', self.path)
        event.reset_mock()
        run.return_value.stdout = 'Volume: 0.10'
        play_track(self.path, 35, run, Mock(), Mock(), event=event)
        self.assertEqual(event.call_args.args[0], 'failed')

    def test_reconnects_and_selects_only_target_speaker(self):
        run = Mock(side_effect=[Mock(stdout='Connected: no'), Mock(),
            Mock(stdout='[]'), Mock(stdout=json.dumps([
                {'id': 79, 'info': {'props': {'media.class': 'Audio/Sink', 'node.name': 'auto_null'}}},
                {'id': 43, 'info': {'props': {'media.class': 'Audio/Sink',
                 'node.name': 'bluez_output.74_68_59_AA_5E_05.1'}}}])), Mock()])
        ensure_speaker(run, Mock())
        self.assertEqual(run.call_args.args[0], ['wpctl', 'set-default', '43'])
        self.assertEqual(run.call_args_list[1].args[0][1], 'connect')

    def test_missing_speaker_reports_failure_without_starting_player(self):
        event, execute = Mock(), Mock()
        prepare = Mock(side_effect=OSError('ACTON III indisponible'))
        self.assertEqual(play_track(self.path, 35, Mock(), Mock(), execute,
                                    event=event, prepare=prepare), 1)
        execute.assert_not_called()
        event.assert_called_once_with('failed', self.path, 'ACTON III indisponible')

    def test_dummy_output_is_never_selected(self):
        run = Mock(side_effect=[Mock(stdout='Connected: yes')] + [Mock(stdout='[]')]*10)
        with self.assertRaisesRegex(OSError, 'aucune sortie audio'):
            ensure_speaker(run, Mock())
        self.assertFalse(any(c.args[0][:2] == ['wpctl', 'set-default'] for c in run.call_args_list))
