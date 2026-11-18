from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=ROOT / 'templates')
router = APIRouter(include_in_schema=False)


@router.api_route('/', methods=['GET', 'HEAD'])
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name='dashboard.html')


@router.get('/login')
def login(request: Request):
    if request.app.state.auth.authenticated(request.headers.get('cookie')):
        return RedirectResponse('/', status_code=303)
    return templates.TemplateResponse(request=request, name='login.html')


@router.get('/direct')
def direct(request: Request):
    return templates.TemplateResponse(request=request, name='direct.html',
                                      context={'enabled': request.app.state.settings.live_audio_enabled})


@router.get('/logs')
def logs(request: Request):
    return templates.TemplateResponse(request=request, name='logs.html')


@router.get('/{asset}')
def legacy_asset(asset: str):
    """Keep existing bookmark/cache URLs working during the transition."""
    from fastapi import HTTPException
    aliases = {'app.js': 'js/dashboard.js', 'login.js': 'js/login.js',
               'logs.js': 'js/logs.js', 'style.css': 'css/style.css'}
    if asset not in aliases:
        raise HTTPException(404)
    return FileResponse(ROOT / 'static' / aliases[asset])
