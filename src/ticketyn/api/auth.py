"""Minimal authentication API. No account or role administration UI in Phase 1."""
from typing import Annotated
import math
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func, literal
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityConfig
from ticketyn.security.passwords import verify_password, hash_password, validate_password, PasswordBusy
from ticketyn.security.service import principal, audit, lock_security
from ticketyn.security.memory import SessionLimit

class SafeAuthRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            # Do not let Pydantic input values or exception chains disclose passwords.
            length = request.headers.get('content-length')
            if length and (not length.isdigit() or int(length) > 65536):
                raise HTTPException(413, 'Solicitud demasiado grande')
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    raise HTTPException(413, 'Solicitud demasiado grande')
            request._body = bytes(body)
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(422, 'Datos de autenticación inválidos') from None
            except PasswordBusy:
                raise HTTPException(503, 'Verificación ocupada; intenta nuevamente') from None
            except SQLAlchemyError:
                raise HTTPException(503, 'No se pudo completar la operación de seguridad') from None
        return handler

router = APIRouter(prefix='/api/auth', tags=['authentication'], route_class=SafeAuthRoute)

def security_db(request: Request):
    with request.app.state.security_session_factory() as session:
        yield session

DB = Annotated[Session, Depends(security_db)]

class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(repr=False)
    @field_validator('password')
    @classmethod
    def password_size(cls, value):
        return validate_password(value)

class ChangePassword(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(repr=False)
    new_password: str = Field(repr=False)
    @field_validator('current_password', 'new_password')
    @classmethod
    def password_size(cls, value):
        return validate_password(value)


def view(request, user=None, item=None):
    user = user or request.state.principal
    item = item or request.state.login_session
    return {'responsible_id': user.id, 'username': user.username, 'name': user.name,
            'role': user.role, 'role_revision': user.role_revision,
            'password_change_required': user.temporary,
            'operational_access': bool(user.permissions) and not user.temporary,
            'role_id': user.role_id, 'permissions': sorted(user.permissions),
            'expires_in': max(0, user.idle_seconds - (request.app.state.security.clock() - item.last_activity)),
            'warning_seconds': 120}


@router.post('/login')
def login(payload: Login, request: Request, session: DB):
    memory = request.app.state.security
    username = payload.username
    ip = request.client.host if request.client else ''
    waiting = memory.wait(username, ip)
    if waiting:
        raise HTTPException(429, 'Demasiados intentos; espera antes de continuar', headers={'Retry-After': str(math.ceil(waiting))})
    account = session.scalar(select(Responsible).where(func.lower(Responsible.username.collate('C.utf8')) == func.lower(literal(username).collate('C.utf8'))))
    # Read snapshot, hash outside a DB transaction, then lock and recheck credentials.
    account_id = account.id if account else None
    encoded = account.password_hash if account else None
    revision = account.access_revision if account else None
    session.rollback()
    correct = verify_password(encoded, payload.password)
    if not correct or account_id is None:
        if memory.failed(username, ip):
            audit(session, 'LOGIN_FAILED_GROUP', success=False, details={'username': username, 'ip': ip[:64], 'operation': 'LOGIN'})
            session.commit()
        raise HTTPException(401, 'Usuario o contraseña incorrectos')
    account = session.scalar(select(Responsible).where(Responsible.id == account_id).with_for_update(of=Responsible))
    user = principal(session, account_id)
    if user is None or account.access_revision != revision or account.password_hash != encoded:
        if memory.failed(username, ip):
            audit(session, 'LOGIN_FAILED_GROUP', success=False, details={'username': username, 'ip': ip[:64], 'operation': 'LOGIN'})
            session.commit()
        raise HTTPException(401, 'Usuario o contraseña incorrectos')
    token = None
    try:
        token = memory.create(user.id, user.revision, ip, request.headers.get('user-agent', ''), idle=user.idle_seconds)
        item = memory.get(token, user.idle_seconds)
        if item is None:
            raise HTTPException(401, 'La sesión fue invalidada; inicia sesión nuevamente')
        audit(session, 'LOGIN_SUCCEEDED', user.id, user.id, details={'username': user.username, 'ip': ip[:64]})
        session.commit()
    except SessionLimit as error:
        session.rollback()
        raise HTTPException(409, str(error)) from None
    except Exception:
        if token is not None:
            memory.revoke(token)
        session.rollback()
        raise
    memory.succeeded(username, ip)
    return {'token': token, **view(request, user, item)}


@router.get('/me')
def me(request: Request):
    return view(request)


@router.post('/activity')
def activity(request: Request):
    # Only explicit, user-driven frontend activity calls this endpoint.
    request.app.state.security.touch(request.state.login_session)
    return view(request)


@router.post('/logout')
def logout(request: Request, session: DB):
    user = request.state.principal
    audit(session, 'SESSION_CLOSED', user.id, user.id)
    session.commit()
    request.app.state.security.revoke(request.state.session_token)
    return {'closed': True}


@router.post('/password')
def password(payload: ChangePassword, request: Request, session: DB):
    user = request.state.principal
    memory = request.app.state.security
    ip = request.client.host if request.client else ''
    waiting = memory.wait(user.username.lower(), ip)
    if waiting:
        raise HTTPException(429, 'Demasiados intentos; espera antes de continuar', headers={'Retry-After': str(math.ceil(waiting))})
    account = session.get(Responsible, user.id)
    encoded = account.password_hash
    session.rollback()
    if not verify_password(encoded, payload.current_password):
        if memory.failed(user.username.lower(), ip):
            audit(session, 'LOGIN_FAILED_GROUP', actor_id=user.id, success=False, details={'username': user.username, 'ip': ip[:64], 'operation': 'PASSWORD_CHANGE'})
            session.commit()
        raise HTTPException(422, 'La contraseña actual es incorrecta')
    new_hash = hash_password(payload.new_password)
    lock_security(session)
    account = session.scalar(select(Responsible).where(Responsible.id == user.id).with_for_update(of=Responsible))
    if account.access_revision != user.revision or account.password_hash != encoded or not account.active or not account.access_granted:
        raise HTTPException(401, 'La cuenta cambió; inicia sesión nuevamente')
    account.password_hash = new_hash
    account.password_change_required = False
    account.access_revision += 1
    revision = account.access_revision
    audit(session, 'PASSWORD_CHANGED', user.id, user.id)
    session.commit()
    memory = request.app.state.security
    memory.succeeded(user.username.lower(), ip)
    memory.revoke_account(user.id, keep=memory.digest(request.state.session_token), revision=revision)
    user = principal(session, user.id)
    return view(request, user)
