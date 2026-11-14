import datetime as dt
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from http.server import ThreadingHTTPServer

from web_server import dashboard_data, make_handler


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        (self.directory / 'recordings').mkdir()
        self.date = '2026-11-14'
        (self.directory / f'bark_log_{self.date}.txt').write_text(
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

    def test_stats_and_recording_metadata(self):
        data = dashboard_data(self.directory, self.date)
        self.assertEqual(data['summary']['detections'], 3)
        self.assertEqual(data['summary']['hours'][8], 2)
        self.assertEqual(data['summary']['sessions'], 1)
        self.assertEqual(data['summary']['seconds'], 2)
        self.assertEqual(data['summary']['recordings'], 1)
        self.assertEqual(data['recordings'][0]['duration'], 60)
        self.assertEqual(dashboard_data(self.directory, '2026-11-13')['recordings'], [])

    def test_trends_fill_calendar_and_aggregate_hours(self):
        (self.directory / 'bark_log_2026-11-13.txt').write_text(
            '[BARKING DETECTED] 2026-11-13 08:10:00 detected (volume: 0.1000)\n'
            '[BARK SESSION] From 2026-11-13 08:10:00 to 2026-11-13 08:12:30 (Duration: 60.0 seconds, 2 barks)\n')
        (self.directory / 'bark_log_2026-11-01.txt').write_text(
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

    def test_authentication_covers_api_audio_and_logout(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.directory, '1234'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = http.client.HTTPConnection(*server.server_address)
        def call(method, path, body=None, headers=None):
            client.request(method, path, body=body, headers=headers or {})
            response = client.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            return result
        try:
            self.assertEqual(call('GET', '/')[0], 303)
            for method in ('GET', 'HEAD'):
                for path in ('/api/dashboard', '/audio/'+self.name, '/app.js'):
                    self.assertEqual(call(method, path)[0], 401)
            self.assertEqual(call('GET', '/login')[0], 200)
            self.assertEqual(call('GET', '/login.js')[0], 200)
            self.assertEqual(call('POST', '/api/login', '{"pin":"1234"}', {'Origin':'http://evil.example'})[0], 403)
            status, headers, _ = call('POST', '/api/login', '{"pin":"1234"}')
            self.assertEqual(status, 200)
            cookie = headers['Set-Cookie']
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=Strict', cookie)
            self.assertNotIn('1234', cookie)
            session = {'Cookie':cookie.split(';')[0]}
            self.assertEqual(call('GET', '/api/dashboard', headers=session)[0], 200)
            self.assertEqual(call('GET', '/audio/'+self.name, headers=dict(session, Range='bytes=0-43'))[0], 206)
            self.assertEqual(call('GET', '/.env', headers=session)[0], 404)
            status, headers, _ = call('POST', '/api/login', '{"pin":"0000"}')
            self.assertEqual(status, 401)
            self.assertEqual(headers['Retry-After'], '2')
            self.assertEqual(call('POST', '/api/login', '{"pin":"1234"}')[0], 429)
            self.assertEqual(call('POST', '/api/logout', headers=session)[0], 200)
            self.assertEqual(call('GET', '/api/dashboard', headers=session)[0], 401)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_http_audio_seeking_and_path_restrictions(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.directory, '1234'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = http.client.HTTPConnection(*server.server_address)
        def get(path, headers=None, method='GET'):
            client.request(method, path, headers=headers or {})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        try:
            client.request('POST', '/api/login', body=json.dumps({'pin':'1234'}), headers={'Content-Type':'application/json'})
            login = client.getresponse()
            self.assertEqual(login.status, 200)
            cookie = login.getheader('Set-Cookie').split(';')[0]
            login.read()
            original_get = get
            def get(path, headers=None, method='GET'):
                return original_get(path, dict({'Cookie':cookie}, **(headers or {})), method)
            status, _, body = get('/api/dashboard?date='+self.date)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['summary']['detections'], 3)
            status, headers, body = get('/audio/'+self.name, {'Range':'bytes=44-75'})
            self.assertEqual(status, 206)
            self.assertEqual(len(body), 32)
            self.assertEqual(headers['Content-Range'], 'bytes 44-75/1920044')
            self.assertEqual(get('/audio/'+self.name, {'Range':'bytes=-12'})[2], b'\0'*12)
            self.assertEqual(get('/audio/'+self.name, {'Range':'bytes=99999999-'})[0], 416)
            self.assertEqual(get('/audio/'+self.name, method='HEAD')[2], b'')
            for path in ('/audio/../README.md', '/audio/%2e%2e%2fREADME.md', '/README.md', '/.git/config'):
                self.assertEqual(get(path)[0], 404)
            self.assertEqual(get('/api/dashboard?date=oops')[0], 400)
            self.assertEqual(get('/api/dashboard?period=30')[0], 200)
            for period in ('0', '365', 'bad'):
                self.assertEqual(get('/api/dashboard?period='+period)[0], 400)
            for path in ('/', '/app.js', '/style.css'):
                self.assertEqual(get(path)[0], 200)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
