"""Application composition. No TensorFlow or hardware imports in the web app."""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.controllers import auth, dashboard, logs, pages, recordings
from app.infrastructure.database import Database
from app.services.auth import Auth
from app.services.dashboard import Dashboard
from app.services.migration import initialize


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    pin = settings.require_pin()

    @asynccontextmanager
    async def lifespan(app):
        database = Database(settings.data_dir)
        try:
            initialize(database)
            app.state.database = database
            app.state.dashboard = Dashboard(database)
            yield
        finally:
            database.close()

    app = FastAPI(title='À l’écoute', version='2.0.0', lifespan=lifespan)
    app.state.settings = settings
    app.state.auth = Auth(pin)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never echo submitted credentials or other raw inputs in error responses.
        return JSONResponse({'error': 'Paramètres de requête invalides.'}, status_code=400)

    @app.middleware('http')
    async def access(request: Request, call_next):
        path = request.url.path
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if (request.headers.get('sec-fetch-site') == 'cross-site'
                    or (origin and urlsplit(origin).netloc != request.headers.get('host'))):
                return JSONResponse({'error': 'Origine refusée.'}, status_code=403)
        public = path in ('/login', '/api/login', '/login.js', '/style.css',
                          '/static/js/login.js', '/static/js/shared/http.js', '/static/css/style.css')
        if not public and not app.state.auth.authenticated(request.headers.get('cookie')):
            if path in ('/', '/logs'):
                return RedirectResponse('/login', status_code=303)
            return JSONResponse({'error': 'Authentification requise.'}, status_code=401)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.method == 'HEAD':
            # Starlette file responses already handle HEAD; JSON endpoints need it too.
            async def empty_body():
                if False:
                    yield b''
            response.body_iterator = empty_body()
        return response

    for router in (auth.router, dashboard.router, recordings.router, logs.router, pages.router):
        app.include_router(router)
    app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
    return app
