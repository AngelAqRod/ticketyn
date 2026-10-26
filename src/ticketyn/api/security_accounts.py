"""Scoped account/profile/session contracts. No additional people or session tables."""
from datetime import datetime, timezone, timedelta
import secrets
from typing import Annotated, Literal
from fastapi import APIRouter, Request, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from ticketyn.api.auth import DB, SafeAuthRoute
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityConfig
from ticketyn.security import accounts, roles
from ticketyn.security.service import principal, audit, lock_security, reset_password
from ticketyn.security.passwords import validate_password, hash_password

router = APIRouter(prefix='/api', tags=['accounts-and-sessions'], route_class=SafeAuthRoute)
Id = Annotated[int, Path(gt=0)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=100)
    role_id: int = Field(gt=0)
    password: str | None = Field(default=None, repr=False)
    access_granted: bool = False

    @field_validator('username')
    @classmethod
    def valid_username(cls, value):
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Usuario inválido')
        return value

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        return validate_password(value) if value is not None else None


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str | None = Field(default=None, min_length=1, max_length=100)
    role_id: int | None = Field(default=None, gt=0)
    access_granted: bool | None = None

    @field_validator('username')
    @classmethod
    def valid_username(cls, value):
        return AccountCreate.valid_username(value) if value is not None else None


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str | None = Field(default=None, repr=False)

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        return validate_password(value) if value is not None else None


@router.get('/responsibles/access')
def account_list(request: Request, session: DB, limit: Annotated[int, Query(ge=1, le=200)] = 50,
                 offset: Annotated[int, Query(ge=0)] = 0):
    # Scope before pagination: equivalent/superior accounts never leak metadata.
    actor = request.state.principal
    rows = session.scalars(select(Responsible).order_by(Responsible.name, Responsible.id))
    result, eligible = [], 0
    for item in rows:
        try:
            roles.authorize_account_change(session, actor, item)
        except HTTPException as error:
            if error.status_code != 403:
                raise
            continue
        if eligible >= offset:
            result.append(accounts.account_view(session, item))
        eligible += 1
        if len(result) == limit:
            break
    return result


@router.get('/responsibles/{id}/access')
def account_detail(id: Id, request: Request, session: DB):
    item = session.get(Responsible, id)
    if item is None:
        raise HTTPException(404, 'Responsable no encontrado')
    roles.authorize_account_change(session, request.state.principal, item)
    return accounts.account_view(session, item)


@router.post('/responsibles/{id}/access', status_code=201)
def account_create(id: Id, payload: AccountCreate, request: Request, session: DB):
    # The only plaintext password response is this newly issued temporary value.
    # Hash before taking the security transaction lock.
    password = payload.password if payload.password is not None else secrets.token_urlsafe(24)
    encoded = hash_password(password)
    item = accounts.create_account(session, request.state.principal.id, id, payload.username,
                                   payload.role_id, encoded, payload.access_granted)
    session.commit()
    return {**accounts.account_view(session, item), 'temporary_password': password}


@router.patch('/responsibles/{id}/access')
def account_update(id: Id, payload: AccountUpdate, request: Request, session: DB):
    values = payload.model_dump(exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(422, 'Los campos de cuenta no admiten null')
    item = accounts.update_account(session, request.state.principal.id, id, values)
    revision = item.access_revision
    session.commit()
    # Revision changes protect other processes/CLI too. Remove local entries promptly.
    with request.app.state.security.lock:
        ids = {s.id for s in request.app.state.security.snapshot() if s.responsible_id == id and s.revision != revision}
        request.app.state.security.revoke_ids(ids)
    return accounts.account_view(session, item)


@router.post('/responsibles/{id}/access/password')
def account_password(id: Id, payload: PasswordReset, request: Request, session: DB):
    password = payload.password if payload.password is not None else secrets.token_urlsafe(24)
    # Recheck actor after acquiring the same lock used for role/access changes.
    actor, _ = accounts.locked_account(session, request.state.principal.id, id)
    reset_password(session, id, password, actor.id)
    session.commit()
    request.app.state.security.revoke_account(id)
    return {'temporary_password': password, 'password_change_required': True}


@router.get('/auth/profile')
def profile(request: Request, session: DB):
    item = session.get(Responsible, request.state.principal.id)
    result = accounts.account_view(session, item)
    # Only the account owner can inspect this safe profile, never arbitrary ids.
    return {**result, 'preferences': {'home_page': item.preferred_home_page}}


class ProfilePreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    home_page: Literal['DASHBOARD', 'MY_TICKETS']


@router.patch('/auth/profile/preferences')
def update_profile_preferences(payload: ProfilePreferences, request: Request, session: DB):
    lock_security(session)
    actor = principal(session, request.state.principal.id)
    if actor is None:
        raise HTTPException(401, 'La cuenta ya no tiene acceso')
    item = session.scalar(select(Responsible).where(Responsible.id == actor.id).with_for_update(of=Responsible))
    item.preferred_home_page = payload.home_page
    session.commit()
    return {'home_page': payload.home_page}


def session_rows(request, session, *, administrative=False):
    memory = request.app.state.security
    snapshots = memory.snapshot()
    if not administrative:
        snapshots = [s for s in snapshots if s.responsible_id == request.state.principal.id]
    if not snapshots:
        return []
    ids = {s.responsible_id for s in snapshots}
    people = {p.id: p for p in session.scalars(select(Responsible).where(Responsible.id.in_(ids)))}
    idle = session.get(SecurityConfig, 1).idle_minutes * 60
    now = memory.clock()
    result = []
    for item in snapshots:
        person = people.get(item.responsible_id)
        if (person is None or not person.active or not person.access_granted or person.access_revision != item.revision
                or now - item.last_activity >= idle):
            continue
        if administrative:
            try:
                roles.authorize_account_change(session, request.state.principal, person, permission='sessions.manage')
            except HTTPException as error:
                if error.status_code != 403:
                    raise
                continue
        result.append({'id': item.id, 'responsible_id': person.id, 'name': person.name, 'username': person.username,
                       'current': item.id == request.state.login_session.id, 'ip': item.ip, 'agent': item.agent,
                       'last_activity': (datetime.now(timezone.utc) - timedelta(seconds=max(0, now - item.last_activity))).isoformat(),
                       'expires_in': max(0, idle - (now - item.last_activity))})
    return sorted(result, key=lambda row: (row['last_activity'], row['id']), reverse=True)


@router.get('/auth/sessions')
def own_sessions(request: Request, session: DB):
    return session_rows(request, session)


@router.get('/security/sessions')
def administrative_sessions(request: Request, session: DB):
    return session_rows(request, session, administrative=True)


def close_sessions(request, session, ids, *, administrative=False):
    lock_security(session)
    # Recheck both requester and target authority under the administrative lock.
    actor = principal(session, request.state.principal.id)
    if actor is None or actor.revision != request.state.principal.revision:
        raise HTTPException(401, 'La cuenta cambió; inicia sesión nuevamente')
    request.state.principal = actor
    if administrative:
        roles.require(actor, 'sessions.manage')
    rows = session_rows(request, session, administrative=administrative)
    selected = [row for row in rows if row['id'] in ids]
    if len(selected) != len(ids):
        raise HTTPException(404, 'La sesión ya no está activa o no puedes administrarla')
    for row in selected:
        audit(session, 'SESSION_TERMINATED_ADMIN' if administrative else 'SESSION_CLOSED', row['responsible_id'], actor.id)
    session.commit()
    request.app.state.security.revoke_ids(ids)
    return {'closed': len(selected)}


@router.post('/auth/sessions/close-others')
def close_others(request: Request, session: DB):
    ids = {s.id for s in request.app.state.security.snapshot()
           if s.responsible_id == request.state.principal.id and s.id != request.state.login_session.id}
    # Only ids still valid under the account's current revision are actionable.
    valid = {row['id'] for row in session_rows(request, session)}
    return close_sessions(request, session, ids & valid)


@router.post('/auth/sessions/{session_id}/revoke')
def close_own(session_id: Annotated[str, Path(pattern=r'^[a-f0-9]{32}$')], request: Request, session: DB):
    return close_sessions(request, session, {session_id})


@router.post('/security/sessions/{session_id}/revoke')
def close_administrative(session_id: Annotated[str, Path(pattern=r'^[a-f0-9]{32}$')], request: Request, session: DB):
    return close_sessions(request, session, {session_id}, administrative=True)
