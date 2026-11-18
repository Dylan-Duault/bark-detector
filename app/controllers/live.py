"""Authenticated SDP signaling and short-lived TURN configuration."""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.history import History

router = APIRouter(prefix='/api/live', tags=['Direct'])
logger = logging.getLogger(__name__)


def require_live(request):
    settings = request.app.state.settings
    if not settings.live_audio_enabled:
        raise HTTPException(404, 'Le direct est désactivé.')
    return settings


async def turn(settings):
    try:
        from app.services.live import ice_servers
    except ImportError as error:
        raise HTTPException(503, 'Installez la dépendance audio du direct.') from error
    try:
        return await asyncio.to_thread(ice_servers, settings)
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(503, 'Le relais TURN est indisponible.') from error


@router.post('/configuration')
async def configuration(request: Request):
    return {'iceServers': await turn(require_live(request))}


@router.post('/offer')
async def offer(request: Request):
    settings = require_live(request)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 24000:
            raise HTTPException(413, 'Offre audio trop volumineuse.')
        body.extend(chunk)
    try:
        sdp = json.loads(body)['sdp']
        media = [line.split()[0] for line in sdp.splitlines() if line.startswith('m=')]
        if sorted(media) != ['m=application', 'm=audio']:
            raise ValueError()
    except (TypeError, ValueError, AttributeError, KeyError, IndexError) as error:
        raise HTTPException(400, 'Offre audio invalide.') from error

    state = request.app.state
    if state.live_busy:
        raise HTTPException(409, 'Une session en direct est déjà ouverte.')
    state.live_busy = True
    session = None
    try:
        ice = await turn(settings)
        from aiortc import RTCSessionDescription
        from app.services.live import LiveSession

        cookie = request.headers.get('cookie')
        session = LiveSession(settings, lambda: state.auth.authenticated(cookie), ice,
                              History(state.database).live_voice)
        await session.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type='offer'))
        async with asyncio.timeout(12):
            await session.pc.setLocalDescription(await session.pc.createAnswer())
        answer = session.pc.localDescription
        state.live_task = asyncio.create_task(watch_session(state, session))
        return {'sdp': answer.sdp, 'type': answer.type}
    except BaseException as error:
        try:
            if session is not None:
                await session.close()
        finally:
            state.live_busy = False
        if isinstance(error, (HTTPException, asyncio.CancelledError)):
            raise
        if isinstance(error, (ValueError, AssertionError)):
            raise HTTPException(400, 'Offre audio invalide.') from error
        if not isinstance(error, Exception):
            raise
        logger.warning('Impossible de créer une session WebRTC (%s)', type(error).__name__)
        raise HTTPException(503, 'Impossible de démarrer le direct.') from error


async def watch_session(state, session):
    try:
        await session.watch()
    finally:
        state.live_busy = False
