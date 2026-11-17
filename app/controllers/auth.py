from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.schemas import LoginRequest
from app.services.auth import COOKIE, SESSION_SECONDS

router = APIRouter(prefix='/api', tags=['Authentication'])


@router.post('/login')
async def login(request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 1024:
            return JSONResponse({'error': 'Requête trop volumineuse.'}, status_code=413)
    try:
        credentials = LoginRequest.model_validate_json(payload)
    except ValidationError:
        return JSONResponse({'error': 'Saisissez un code à quatre chiffres.'}, status_code=400)
    ip = request.client.host if request.client else 'local'
    token, delay, blocked = request.app.state.auth.login(ip, credentials.pin)
    if token is None:
        return JSONResponse({'error': 'Veuillez patienter.' if blocked else 'Code incorrect.', 'retry_after': delay},
                            status_code=429 if blocked else 401, headers={'Retry-After': str(delay)})
    response = JSONResponse({'ok': True})
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        samesite='strict', secure=request.app.state.settings.cookie_secure)
    return response


@router.post('/logout')
def logout(request: Request):
    request.app.state.auth.logout(request.headers.get('cookie'))
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE, httponly=True, samesite='strict',
                           secure=request.app.state.settings.cookie_secure)
    return response
