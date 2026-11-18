"""Local audio exchange between the detector and the authenticated web process."""
import fcntl
import socket


def mic_socket(directory):
    return directory / '.live-microphone.sock'


def voice_lock(directory):
    return (directory / '.live-voice.lock').open('ab')


class MicrophoneFeed:
    def __init__(self, directory):
        self.address = str(mic_socket(directory))
        self.voice = voice_lock(directory)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)

    def publish(self, samples):
        # PortAudio must never wait for the web process.
        try:
            self.socket.sendto(samples.tobytes(), self.address)
        except OSError:
            pass

    def speaking(self):
        try:
            fcntl.flock(self.voice, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(self.voice, fcntl.LOCK_UN)
        return False

    def close(self):
        self.socket.close()
        self.voice.close()
