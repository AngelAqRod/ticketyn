"""Mail administration under Ticketyn's existing trusted-network access model.

There is no individual authorization mechanism. SMTP tests and persistent jobs
share the transport; FMS creation requests automatic work transactionally.
"""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from ticketyn.api.crud import DBSession
from ticketyn.core.secret_store import SecretError, get_secret_cipher
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications.coordination import ensure_idle
from ticketyn.notifications.fields import EVENTS, FIELD_REGISTRY
from ticketyn.schemas.mail_notifications import DynamicFieldResponse, EventResponse, EventUpdate, SmtpResponse, SmtpUpdate

from ticketyn.schemas.mail_templates import MailTemplate, PreviewRequest, PreviewResponse
from ticketyn.notifications.templates import render_template, validate_template
from ticketyn.api.fms_data import operation_query
from ticketyn.api.reports import read_snapshot
from ticketyn.models.fms import Activation


from ticketyn.notifications.delivery import PASSWORD_CONTEXT


class SafeMailRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def safe(request):
            try:
                return await original(request)
            except RequestValidationError as error:
                # FastAPI's default errors can include raw request input/passwords.
                detail = [{'loc': item['loc'], 'type': item['type'], 'msg': item['msg']} for item in error.errors()]
                raise HTTPException(422, detail) from None
            except SecretError:
                raise HTTPException(503, 'No se pudo proteger la credencial. Revisa el archivo de claves y sus permisos.') from None
            except SQLAlchemyError:
                raise HTTPException(503, 'No se pudo guardar o consultar la configuración de correo.') from None
        return safe


router = APIRouter(prefix='/api/mail-notifications', tags=['mail-notifications'], route_class=SafeMailRoute)


def smtp_response(row):
    if row is None:
        return SmtpResponse()
    values = {field: getattr(row, field) for field in ('host', 'port', 'security', 'allow_unencrypted', 'sender_email', 'sender_name', 'auth_method', 'provider', 'username')}
    return SmtpResponse(**values, password_configured=bool(row.smtp_password_encrypted),
                        oauth_credentials_configured=bool(row.oauth_credentials_encrypted),
                        configured=bool(row.host and row.sender_email))


@router.get('/smtp', response_model=SmtpResponse)
def get_smtp(session: DBSession):
    return smtp_response(session.get(MailTransportConfig, 1))


@router.patch('/smtp', response_model=SmtpResponse)
def update_smtp(payload: SmtpUpdate, session: DBSession):
    try:
        session.execute(insert(MailTransportConfig).values(id=1).on_conflict_do_nothing(index_elements=['id']))
        row = session.scalar(select(MailTransportConfig).where(MailTransportConfig.id == 1).with_for_update().execution_options(populate_existing=True))
        ensure_idle(row)
        previous_binding = (row.auth_method, row.provider, row.username)
        values = payload.model_dump(exclude_unset=True, exclude={'smtp_password', 'clear_password'})
        for key, value in values.items():
            setattr(row, key, value)
        if not row.host or not row.sender_email:
            raise HTTPException(422, 'Completa el servidor SMTP y la dirección del remitente.')
        if row.security == 'NONE' and not row.allow_unencrypted:
            raise HTTPException(422, 'La conexión sin cifrado requiere autorizar expresamente un relé local o confiable.')
        if row.security == 'NONE' and row.auth_method != 'NONE':
            raise HTTPException(422, 'No se permiten credenciales ni tokens sobre SMTP sin cifrado.')
        if previous_binding != (row.auth_method, row.provider, row.username):
            row.oauth_credentials_encrypted = None
            row.oauth_settings = {}
            row.oauth_status = 'UNCONFIGURED'
            if previous_binding[2] != row.username or previous_binding[1] != row.provider:
                row.smtp_password_encrypted = None
        if payload.clear_password and 'smtp_password' in payload.model_fields_set:
            raise HTTPException(422, 'No puedes guardar y eliminar la contraseña en la misma solicitud.')
        if row.auth_method.startswith('OAUTH2'):
            if row.provider is None:
                raise HTTPException(422, 'Selecciona el proveedor para la configuración OAuth2.')
            if row.auth_method == 'OAUTH2_APPLICATION' and row.provider not in {'GOOGLE_WORKSPACE', 'MICROSOFT_365'}:
                raise HTTPException(422, 'Este proveedor no admite el perfil OAuth2 de aplicación disponible.')
        if 'smtp_password' in payload.model_fields_set:
            if row.auth_method != 'PASSWORD':
                raise HTTPException(422, 'La contraseña SMTP solo se configura con autenticación de usuario y contraseña.')
            row.smtp_password_encrypted = get_secret_cipher().encrypt(payload.smtp_password.get_secret_value(), context=PASSWORD_CONTEXT)
        if payload.clear_password:
            row.smtp_password_encrypted = None
        if row.auth_method == 'PASSWORD' and (not row.username or not row.username.strip() or not row.smtp_password_encrypted):
            raise HTTPException(422, 'La autenticación por contraseña requiere usuario y una contraseña configurada.')
        session.commit()
        session.refresh(row)
        return smtp_response(row)
    except Exception:
        session.rollback()
        raise


def known_event(event_key):
    if event_key not in EVENTS:
        raise HTTPException(404, 'El evento de notificación no existe.')


def event_response(event_key, row):
    return EventResponse(event_key=event_key, label=EVENTS[event_key],
                         **({'mode': row.mode, 'to': row.to_recipients, 'cc': row.cc_recipients, 'bcc': row.bcc_recipients} if row else {}))


@router.get('/events', response_model=list[EventResponse])
def events(session: DBSession):
    rows = {row.event_key: row for row in session.scalars(select(MailEventConfig).where(MailEventConfig.event_key.in_(EVENTS)))}
    return [event_response(key, rows.get(key)) for key in EVENTS]


@router.get('/events/{event_key}', response_model=EventResponse)
def get_event(event_key: str, session: DBSession):
    known_event(event_key)
    return event_response(event_key, session.get(MailEventConfig, event_key))


@router.patch('/events/{event_key}', response_model=EventResponse)
def update_event(event_key: str, payload: EventUpdate, session: DBSession):
    known_event(event_key)
    try:
        from ticketyn.notifications.requests import control_row, cancel_unstarted
        control = control_row(session)
        session.execute(insert(MailEventConfig).values(event_key=event_key).on_conflict_do_nothing(index_elements=['event_key']))
        row = session.scalar(select(MailEventConfig).where(MailEventConfig.event_key == event_key).with_for_update().execution_options(populate_existing=True))
        previous_mode = row.mode
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, {'to': 'to_recipients', 'cc': 'cc_recipients', 'bcc': 'bcc_recipients'}.get(key, key), value)
        if row.mode == 'DISABLED' or (previous_mode == 'AUTOMATIC' and row.mode == 'MANUAL'):
            cancel_unstarted(session, control, event_key, include_manual=row.mode == 'DISABLED')
        session.commit()
        session.refresh(row)
        return event_response(event_key, row)
    except Exception:
        session.rollback()
        raise


@router.get('/events/{event_key}/fields', response_model=list[DynamicFieldResponse])
def fields(event_key: str):
    known_event(event_key)
    return [asdict(field) for field in FIELD_REGISTRY[event_key]]


# Templates are configuration; previews are ephemeral and never stored.


@router.get('/events/{event_key}/template', response_model=MailTemplate)
def get_template(event_key: str, session: DBSession):
    known_event(event_key)
    row = session.get(MailEventConfig, event_key)
    return MailTemplate.model_validate(row.template) if row and row.template is not None else MailTemplate()


@router.patch('/events/{event_key}/template', response_model=MailTemplate)
def save_template(event_key: str, payload: MailTemplate, session: DBSession):
    known_event(event_key)
    validate_template(event_key, payload)
    try:
        session.execute(insert(MailEventConfig).values(event_key=event_key).on_conflict_do_nothing(index_elements=['event_key']))
        row = session.scalar(select(MailEventConfig).where(MailEventConfig.event_key == event_key).with_for_update().execution_options(populate_existing=True))
        row.template = payload.model_dump()
        session.commit()
        return payload
    except Exception:
        session.rollback()
        raise


@router.post('/events/{event_key}/preview', response_model=PreviewResponse)
def preview_template(event_key: str, payload: PreviewRequest, session: DBSession):
    known_event(event_key)
    validate_template(event_key, payload.template)
    read_snapshot(session)
    activation = session.scalar(operation_query(Activation).where(Activation.id == payload.activation_id))
    if activation is None:
        raise HTTPException(404, 'La activación seleccionada no existe.')
    return render_template(session, event_key, payload.template, activation)
