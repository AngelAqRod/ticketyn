"""Fail-closed HTTP boundary, independent from operational transaction sessions."""
from contextlib import contextmanager
import asyncio
import os
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ticketyn.security.memory import MemorySecurity
from ticketyn.security.service import principal
from ticketyn.security.routes import resolve, allowed

AUTH_PATHS = {'/api/auth/me', '/api/auth/logout', '/api/auth/password', '/api/auth/activity'}
CALLBACK = '/api/mail-notifications/oauth/callback'

@contextmanager
def default_session():
    from ticketyn.db.session import get_engine
    with Session(get_engine()) as session:
        yield session


def authenticate(app, token=None, flow=None):
    memory = app.state.security
    item = flow or memory.get(token or '', idle=86400)
    if item is None:
        return None
    with app.state.security_session_factory() as session:
        user = principal(session, item.responsible_id)
    if user is None or user.revision != item.revision or memory.clock() - item.last_activity >= user.idle_seconds:
        memory.revoke(token or '')
        return None
    with memory.lock:
        item.idle_seconds = user.idle_seconds
    return user, item


class SecurityBoundary(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if (path == '/health' and request.method in {'GET', 'HEAD'}) or (path == '/api/auth/login' and request.method == 'POST'):
            response = await call_next(request)
        else:
            authorization = request.headers.get('authorization', '')
            token = authorization[7:] if authorization.startswith('Bearer ') else ''
            flow = None
            if path == CALLBACK and request.method == 'GET':
                from ticketyn.notifications.oauth import COOKIE_NAME
                flow = request.app.state.security.flow_session(request.cookies.get(COOKIE_NAME, ''))
                if flow is None:
                    return JSONResponse({'detail': 'El flujo OAuth2 no tiene una sesión autorizada vigente'}, status_code=401, headers={'Cache-Control': 'no-store'})
            try:
                result = await run_in_threadpool(authenticate, request.app, token, flow)
            except SQLAlchemyError:
                return JSONResponse({'detail': 'No se pudo verificar el acceso'}, status_code=503, headers={'Cache-Control': 'no-store'})
            if result is None:
                return JSONResponse({'detail': 'La sesión no existe, venció o fue invalidada'}, status_code=401, headers={'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer'})
            user, item = result
            resolved = resolve(request.method, path)
            if resolved is None or (user.temporary and path not in AUTH_PATHS) or not allowed(resolved[1], user.permissions, resolved[2], resolved[0]):
                return JSONResponse({'detail': 'No tienes permiso para realizar esta operación'}, status_code=403, headers={'Cache-Control': 'no-store'})
            request.state.principal = user
            request.state.login_session = item
            request.state.session_token = token
            response = await call_next(request)
        if path.startswith('/api/') or path in {'/docs', '/openapi.json', '/redoc'}:
            response.headers['Cache-Control'] = 'no-store'
        return response


def install_security(app, session_factory=None):
    if os.environ.get('WEB_CONCURRENCY', '1') != '1':
        raise RuntimeError('Las sesiones en RAM requieren un único trabajador HTTP')
    app.state.security = MemorySecurity()
    app.state.security_session_factory = session_factory or default_session
    app.add_middleware(SecurityBoundary)


async def cleanup_loop(app, retention=None):
    while True:
        await asyncio.sleep(60)
        app.state.security.cleanup()
        if retention is not None:
            await retention.tick()
