import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import Mock

from app.services.dashboard import dashboard_data
from app.services.recordings import recording_levels
from app.infrastructure.journal import live_logs


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        (self.directory / 'recordings').mkdir()
        (self.directory / 'logs').mkdir()
        self.date = '2026-11-14'
        (self.directory / 'logs' / f'bark_log_{self.date}.txt').write_text(
            '[BARKING DETECTED] 2026-11-14 08:12:00 detected (volume: 0.1000)\n'
            '[BARKING DETECTED] 2026-11-14 08:12:02 detected (volume: 0.1000)\n'
            '[BARKING DETECTED] 2026-11-14 16:12:02 detected (volume: 0.1000)\n'
            '[BARK SESSION] From 2026-11-14 08:12:00 to 2026-11-14 08:13:32 (Duration: 2.0 seconds, 2 barks)\n'
            '[SUMMARY] Session ended | Total barks: 3\n'
            '[BARKING DETECTED] incomplete\n')
        self.name = 'bark_audio_2026-11-14_08-12-02.wav'
        with wave.open(str(self.directory / 'recordings' / self.name), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 16000 * 60)

    def tearDown(self):
        self.tmp.cleanup()

    def test_music_events_are_filtered_by_date_and_ignore_partial_lines(self):
        (self.directory / 'logs' / f'music_{self.date}.jsonl').write_text(
            json.dumps(dict(time='12:00:00', track='calm.mp3', status='started', detail='')) + '\n{partial')
        data = dashboard_data(self.directory, self.date)
        self.assertEqual(data['music_events'][0]['track'], 'calm.mp3')
        self.assertEqual(dashboard_data(self.directory, '2020-01-01')['music_events'], [])

    def test_stats_and_recording_metadata(self):
        data = dashboard_data(self.directory, self.date)
        self.assertEqual(data['summary']['detections'], 3)
        self.assertEqual(data['summary']['hours'][8], 2)
        self.assertEqual(data['summary']['sessions'], 1)
        self.assertEqual(data['summary']['seconds'], 2)
        self.assertEqual(data['summary']['recordings'], 1)
        self.assertEqual(data['recordings'][0]['duration'], 60)
        self.assertEqual(dashboard_data(self.directory, '2026-11-13')['recordings'], [])

    def test_waveform_preserves_peak_position_and_dbfs(self):
        path = self.directory / 'recordings' / self.name
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            # Silence, a half-scale impulse at 1 s, then silence.
            import struct
            audio.writeframes(b'\0\0' * 16000 + struct.pack('<h', 16384) + b'\0\0' * 15999)
        stat = path.stat()
        data = recording_levels(path, stat.st_mtime_ns, stat.st_size)
        self.assertEqual(data['duration'], 2)
        self.assertLessEqual(len(data['levels']), 600)
        self.assertAlmostEqual(data['peak_dbfs'], -6.0, places=1)
        index = data['levels'].index(data['peak_dbfs'])
        self.assertLessEqual(abs(index * data['step'] - 1), data['step'])
        self.assertEqual(data['levels'][0], -60)
        # The cache key changes when an existing file is replaced.
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 16000)
        stat = path.stat()
        silent = recording_levels(path, stat.st_mtime_ns, stat.st_size)
        self.assertEqual(silent['peak_dbfs'], -60)
        self.assertEqual(silent['duration'], 1)

    def test_trends_fill_calendar_and_aggregate_hours(self):
        (self.directory / 'logs' / 'bark_log_2026-11-13.txt').write_text(
            '[BARKING DETECTED] 2026-11-13 08:10:00 detected (volume: 0.1000)\n'
            '[BARK SESSION] From 2026-11-13 08:10:00 to 2026-11-13 08:12:30 (Duration: 60.0 seconds, 2 barks)\n')
        (self.directory / 'logs' / 'bark_log_2026-11-01.txt').write_text(
            '[BARKING DETECTED] 2026-11-01 08:10:00 detected (volume: 0.1000)\n')
        trends = dashboard_data(self.directory, self.date, 7)['trends']
        self.assertEqual(len(trends['days']), 7)
        self.assertEqual(trends['start'], '2026-11-08')
        self.assertEqual(trends['end'], self.date)
        self.assertEqual(trends['hours'][8], 3)
        self.assertEqual(trends['hours'][16], 1)
        self.assertFalse(trends['days'][0]['has_log'])
        self.assertEqual(trends['days'][0]['seconds'], 0)
        self.assertTrue(trends['days'][-2]['has_log'])
        self.assertEqual(trends['days'][-2]['seconds'], 60)
        longer = dashboard_data(self.directory, self.date, 30)['trends']
        self.assertEqual(len(longer['days']), 30)
        self.assertEqual(longer['start'], '2026-10-16')
        self.assertEqual(longer['hours'][8], 4)
        with self.assertRaises(ValueError):
            dashboard_data(self.directory, self.date, 365)

    def test_empty_and_incomplete_files(self):
        (self.directory / 'recordings' / 'bark_audio_2026-11-14_12-00-00.wav').write_bytes(b'RIFF')
        data = dashboard_data(self.directory, self.date)
        self.assertEqual(len(data['recordings']), 1)
        self.assertEqual(dashboard_data(self.directory, '2026-11-13')['summary']['detections'], 0)

    def client(self):
        from fastapi.testclient import TestClient
        from app.config import Settings
        from app.main import create_app
        return TestClient(create_app(Settings(_env_file=None, data_dir=self.directory, dashboard_pin='1234')), follow_redirects=False)

    def test_authentication_covers_api_audio_and_logout(self):
        with self.client() as client:
            self.assertEqual(client.get('/').status_code, 303)
            for method in ('GET', 'HEAD'):
                for path in ('/api/dashboard', '/audio/'+self.name, '/api/waveform/'+self.name, '/app.js', '/docs', '/openapi.json', '/static/js/dashboard.js'):
                    self.assertEqual(client.request(method, path).status_code, 401)
            self.assertEqual(client.get('/login').status_code, 200)
            self.assertEqual(client.get('/login.js').status_code, 200)
            self.assertEqual(client.post('/api/login', json={'pin':'1234'}, headers={'Origin':'http://evil.example'}).status_code, 403)
            response = client.post('/api/login', json={'pin':'1234'})
            self.assertEqual(response.status_code, 200)
            cookie = response.headers['set-cookie']
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=strict', cookie)
            self.assertNotIn('1234', cookie)
            self.assertEqual(client.get('/api/dashboard').status_code, 200)
            self.assertEqual(client.get('/audio/'+self.name, headers={'Range':'bytes=0-43'}).status_code, 206)
            self.assertEqual(client.get('/.env').status_code, 404)
            response = client.post('/api/login', json={'pin':'0000'})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers['Retry-After'], '2')
            self.assertEqual(client.post('/api/login', json={'pin':'1234'}).status_code, 429)
            self.assertEqual(client.post('/api/logout').status_code, 200)
            self.assertEqual(client.get('/api/dashboard').status_code, 401)

    def test_http_audio_seeking_and_path_restrictions(self):
        with self.client() as client:
            self.assertEqual(client.post('/api/login', json={'pin':'1234'}).status_code, 200)
            response = client.get('/api/dashboard?date='+self.date)
            self.assertEqual(response.status_code, 200)
            self.assertIs(response.json()['detector']['healthy'], False)
            self.assertEqual(response.json()['summary']['detections'], 3)
            response = client.get('/api/waveform/'+self.name)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['peak_dbfs'], -60)
            self.assertEqual(client.head('/api/waveform/'+self.name).content, b'')
            response = client.get('/audio/'+self.name, headers={'Range':'bytes=44-75'})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(len(response.content), 32)
            self.assertEqual(response.headers['Content-Range'], 'bytes 44-75/1920044')
            self.assertEqual(client.get('/audio/'+self.name, headers={'Range':'bytes=-12'}).content, b'\0'*12)
            self.assertEqual(client.get('/audio/'+self.name, headers={'Range':'bytes=99999999-'}).status_code, 416)
            self.assertEqual(client.head('/audio/'+self.name).content, b'')
            for path in ('/audio/../README.md', '/audio/%2e%2e%2fREADME.md', '/api/waveform/../README.md', '/README.md', '/.git/config'):
                self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.get('/api/dashboard?date=oops').status_code, 400)
            self.assertEqual(client.get('/api/dashboard?period=30').status_code, 200)
            for period in ('0', '365', 'bad'):
                self.assertEqual(client.get('/api/dashboard?period='+period).status_code, 400)
            for path in ('/', '/logs', '/app.js', '/style.css', '/static/js/components/bark-recording.js'):
                self.assertEqual(client.get(path).status_code, 200)

    def test_invalid_login_payloads_are_bounded_and_never_echoed(self):
        with self.client() as client:
            for payload in ({'pin':1234}, {'pin':'1234', 'extra':'secret'}, {'pin':'secret'}, {}):
                response = client.post('/api/login', json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn('secret', response.text)
            self.assertEqual(client.post('/api/login', content='x'*1025).status_code, 413)
            self.assertEqual(client.post('/api/login', json={'pin':'1234'}, headers={'Sec-Fetch-Site':'cross-site'}).status_code, 403)

    def test_audio_symlinks_and_partial_files_are_not_served(self):
        (self.directory / 'recordings' / 'bark_audio_2026-11-14_09-00-00.wav').symlink_to(self.directory / 'recordings' / self.name)
        with self.client() as client:
            client.post('/api/login', json={'pin':'1234'})
            self.assertEqual(client.get('/audio/bark_audio_2026-11-14_09-00-00.wav').status_code, 404)
            self.assertEqual(client.get('/audio/'+self.name+'.part').status_code, 404)
            self.assertEqual(client.get('/api/dashboard').headers['Cache-Control'], 'no-store')

    def test_web_application_does_not_import_tensorflow(self):
        import subprocess, sys
        result = subprocess.run([sys.executable, '-c',
            "import sys; from app.main import create_app; assert 'tensorflow' not in sys.modules; assert 'sounddevice' not in sys.modules"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()


class LiveLogTests(unittest.TestCase):
    def test_logs_preserve_messages_and_ignore_malformed_entries(self):
        run = Mock(return_value=Mock(returncode=0, stdout=json.dumps({
            '__CURSOR': 'cursor', '__REALTIME_TIMESTAMP': '1000000',
            'MESSAGE': '<script>test</script>', 'PRIORITY': '3'}) + '\ninvalid'))
        result = live_logs('detector', run)
        self.assertEqual(result['entries'][0]['timestamp'], 1)
        self.assertEqual(result['entries'][0]['message'], '<script>test</script>')
        self.assertIn('--unit=bark-detector.service', run.call_args.args[0])

    def test_arbitrary_units_are_rejected(self):
        run = Mock()
        with self.assertRaises(ValueError):
            live_logs('ssh.service', run)
        run.assert_not_called()
