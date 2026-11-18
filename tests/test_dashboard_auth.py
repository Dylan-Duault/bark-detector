from pathlib import Path
import tempfile
import unittest
from app.config import Settings
from app.services.auth import Auth, COOKIE, SESSION_SECONDS


class AuthTests(unittest.TestCase):
    def test_pin_configuration_fails_closed_and_preserves_leading_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            with self.assertRaises(ValueError):
                Settings(_env_file=path).require_pin()
            for invalid in ('', '123', '12345', 'abcd', '１２３４'):
                path.write_text('DASHBOARD_PIN='+invalid)
                with self.assertRaises(ValueError):
                    Settings(_env_file=path).require_pin()
            path.write_text('# Private configuration\nDASHBOARD_PIN="0123"\n')
            self.assertEqual(Settings(_env_file=path).require_pin(), '0123')

    def test_progressive_delay_is_enforced_even_for_correct_pin(self):
        now = [100.0]
        auth = Auth('1234', clock=lambda:now[0])
        for expected in (2, 4, 8, 16, 32, 60, 60):
            token, delay, blocked = auth.login('phone', '0000')
            self.assertIsNone(token)
            self.assertFalse(blocked)
            self.assertEqual(delay, expected)
            self.assertTrue(auth.login('phone', '1234')[2])
            now[0] += expected
        self.assertIsNotNone(auth.login('phone', '1234')[0])
        self.assertEqual(auth.login('phone', '0000')[1], 2)

    def test_cookie_expiry_logout_and_sessions_do_not_contain_pin(self):
        now = [100.0]
        auth = Auth('1234', clock=lambda:now[0])
        token, _, _ = auth.login('phone', '1234')
        cookie = f'{COOKIE}={token}'
        self.assertTrue(auth.authenticated(cookie))
        self.assertFalse(auth.authenticated(f'{COOKIE}=forged'))
        now[0] += SESSION_SECONDS
        self.assertFalse(auth.authenticated(cookie))
        token, _, _ = auth.login('phone', '1234')
        cookie = f'{COOKIE}={token}'
        auth.logout(cookie)
        self.assertFalse(auth.authenticated(cookie))


if __name__ == '__main__':
    unittest.main()
