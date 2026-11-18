import tempfile
import unittest
from pathlib import Path

from app.config import Settings

try:
    from aiortc import RTCBundlePolicy, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from app.services.live import LiveSession
except ImportError:
    HAS_LIVE_AUDIO = False
else:
    HAS_LIVE_AUDIO = True


@unittest.skipUnless(HAS_LIVE_AUDIO, 'Install the live audio extra')
class LiveSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundle_keeps_candidates_from_the_audio_section(self):
        browser = RTCPeerConnection(RTCConfiguration(
            iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE,
        ))
        self.addAsyncCleanup(browser.close)
        browser.addTransceiver('audio')
        browser.createDataChannel('direct')
        await browser.setLocalDescription(await browser.createOffer())
        audio, data = browser.localDescription.sdp.split('m=application', 1)
        self.assertIn('a=candidate:', audio)
        # Browsers can send candidates only on the BUNDLE group's first section.
        data = ''.join(line for line in data.splitlines(keepends=True)
                       if not line.startswith(('a=candidate:', 'a=end-of-candidates')))
        offer = RTCSessionDescription(sdp=audio + 'm=application' + data, type='offer')

        with tempfile.TemporaryDirectory() as directory:
            session = LiveSession(Settings(_env_file=None, data_dir=Path(directory)),
                                  lambda: True, [], lambda _: None)
            try:
                await session.pc.setRemoteDescription(offer)
                transport = session.pc.getTransceivers()[0].receiver.transport.transport
                self.assertIs(session.pc.sctp.transport.transport, transport)
                self.assertTrue(transport.getRemoteCandidates())
            finally:
                await session.close()
            self.assertFalse(session.tasks)
