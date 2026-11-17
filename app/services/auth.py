"""PIN configuration, expiring sessions and server-side login throttling."""
import hmac
from http.cookies import SimpleCookie, CookieError
import re
import secrets
from threading import Lock
import time

COOKIE = 'bark_session'
SESSION_SECONDS = 12 * 3600


def load_pin(path):
    from app.config import Settings
    return Settings(_env_file=path).require_pin()


class Auth:
    def __init__(self, pin, clock=time.monotonic):
        if not re.fullmatch(r'[0-9]{4}', pin):
            raise ValueError('PIN must contain exactly four digits')
        self.pin = pin
        self.clock = clock
        self.lock = Lock()
        self.sessions = {}
        self.failures = {}

    def login(self, ip, pin):
        with self.lock:
            now = self.clock()
            # Expire inactive clients to bound state; do not trust forwarded IP headers.
            self.failures = {key: value for key, value in self.failures.items() if value[1] + 3600 > now}
            self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
            attempts, retry_at = self.failures.get(ip, (0, 0))
            if retry_at > now:
                return None, max(1, int(retry_at - now + .999)), True
            if not isinstance(pin, str) or not hmac.compare_digest(pin.encode(), self.pin.encode()):
                delay = min(60, 2 ** min(attempts + 1, 6))
                self.failures[ip] = (attempts + 1, now + delay)
                return None, delay, False
            self.failures.pop(ip, None)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + SESSION_SECONDS
            return token, 0, False

    def token(self, header):
        cookie = SimpleCookie()
        try:
            cookie.load(header or '')
            return cookie[COOKIE].value if COOKIE in cookie else None
        except CookieError:
            return None

    def authenticated(self, header):
        token = self.token(header)
        with self.lock:
            expiry = self.sessions.get(token, 0)
            if expiry <= self.clock():
                self.sessions.pop(token, None)
                return False
            return True

    def logout(self, header):
        with self.lock:
            self.sessions.pop(self.token(header), None)
