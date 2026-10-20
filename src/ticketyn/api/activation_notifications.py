"""Activation-specific manual intent; never connects to SMTP or changes FMS."""
from typing import Annotated
from fastapi import APIRouter, HTTPException, Path
from pydantic import ValidationError
from sqlalchemy import select
from ticketyn.api.crud import DBSession
from ticketyn.api.fms_data import operation_query
from ticketyn.api.mail_notifications import SafeMailRoute
from ticketyn.api.mail_transport import require_oauth
from ticketyn.models.fms import Activation
from ticketyn.models.mail_jobs import MailNotificationRequest
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications.delivery import transport_settings
from ticketyn.notifications.fields import ACTIVATION_EVENT
from ticketyn.notifications.requests import ACTIVE, control_row, request_notification
from ticketyn.notifications.smtp import MailFailure, build_message
from ticketyn.notifications.templates import render_template
from ticketyn.schemas.activation_notifications import ActivationNotificationStatus, RequestActivationNotification
from ticketyn.schemas.mail_templates import MailTemplate

router = APIRouter(prefix='/api/activations', tags=['activation-notifications'], route_class=SafeMailRoute)
Id = Annotated[int, Path(gt=0)]


def notification_context(session, activation_id):
    # Keep stage 6's lock order. Plain activation reads never lock the circuit.
    control = control_row(session)
    activation = session.scalar(operation_query(Activation).where(Activation.id == activation_id))
    if activation is None:
        raise HTTPException(404, 'La activación no existe.')
    event = session.scalar(select(MailEventConfig).where(MailEventConfig.event_key == ACTIVATION_EVENT)
                           .with_for_update().execution_options(populate_existing=True))
    job = session.scalar(select(MailNotificationRequest).where(
        MailNotificationRequest.event_key == ACTIVATION_EVENT,
        MailNotificationRequest.activation_id == activation_id,
    ).with_for_update().execution_options(populate_existing=True))
    return control, activation, event, job


def configuration_problem(session, event, activation):
    """Read-only preflight with shared validators/rendering. No secret decryption,
    token refresh or network I/O; the worker will re-read current configuration.
    Generated text/MIME is ephemeral and is neither returned nor persisted here.
    """
    row = session.get(MailTransportConfig, 1)
    if row is None:
        return 'Configura el transporte de correo en Administración.'
    try:
        transport_settings(row)
        if row.security == 'NONE' and not row.allow_unencrypted:
            return 'La conexión sin cifrado no está autorizada en la configuración.'
        if row.auth_method == 'PASSWORD' and (not row.username or not row.smtp_password_encrypted):
            return 'Completa el usuario y la contraseña SMTP en Administración.'
        if row.auth_method.startswith('OAUTH2'):
            require_oauth(row)
            settings = row.oauth_settings or {}
            google_app = row.auth_method == 'OAUTH2_APPLICATION' and row.provider == 'GOOGLE_WORKSPACE'
            if not row.oauth_credentials_encrypted:
                return 'Configura las credenciales OAuth2 en Administración.'
            if google_app:
                if not settings.get('service_account_configured'):
                    return 'Configura la cuenta de servicio OAuth2 en Administración.'
            elif not settings.get('client_id') or not settings.get('client_secret_configured'):
                return 'Completa la configuración de la aplicación OAuth2 en Administración.'
            if row.provider == 'MICROSOFT_365' and not settings.get('tenant_id'):
                return 'Completa el tenant de Microsoft 365 en Administración.'
            allowed = {'CONNECTED'} if row.auth_method == 'OAUTH2_DELEGATED' else {'CONFIGURED', 'CONNECTED'}
            if row.oauth_status not in allowed:
                return 'La cuenta OAuth2 requiere configuración o autorización en Administración.'
        if event.template is None:
            return 'Configura la plantilla de correo en Administración.'
        if not any((event.to_recipients, event.cc_recipients, event.bcc_recipients)):
            return 'Configura al menos un destinatario del evento en Administración.'
        content = render_template(session, ACTIVATION_EVENT, MailTemplate.model_validate(event.template), activation)
        if not content.subject.strip() and not content.body.strip():
            return 'La plantilla no genera contenido para esta activación.'
        build_message(sender_email=row.sender_email, sender_name=row.sender_name,
                      to=event.to_recipients, cc=event.cc_recipients, bcc=event.bcc_recipients,
                      subject=content.subject, body=content.body, html_body=content.html_body)
    except (MailFailure, ValidationError, HTTPException, ValueError, TypeError):
        return 'La configuración de correo o la plantilla no es válida. Revísala en Administración.'
    return None


def status_response(session, control, activation, event, job, *, problem=None, checked=False, message=None):
    mode = event.mode if event is not None else 'DISABLED'
    active = job is not None and job.state in ACTIVE
    if mode != 'DISABLED' and not active and not checked:
        problem = configuration_problem(session, event, activation)
    return ActivationNotificationStatus(
        activation_id=activation.id, mode=mode, state=job.state if job else None,
        revision=job.revision if job else 0, processor_paused=control.paused,
        can_request=mode != 'DISABLED' and not active and problem is None,
        configuration_error=problem, message=message,
    )


@router.get('/{id}/notification', response_model=ActivationNotificationStatus)
def get_notification(id: Id, session: DBSession):
    context = notification_context(session, id)
    result = status_response(session, *context)
    session.commit()  # Persist fail-closed restoration detection, if necessary.
    return result


@router.post('/{id}/notification', response_model=ActivationNotificationStatus, status_code=202)
def request_manual_notification(id: Id, payload: RequestActivationNotification, session: DBSession):
    try:
        control, activation, event, job = notification_context(session, id)
        if event is None or event.mode == 'DISABLED':
            raise HTTPException(422, 'El evento de notificación está desactivado.')
        if payload.revision != (job.revision if job else 0):
            raise HTTPException(409, 'La solicitud cambió; actualiza su estado antes de solicitar otro envío.')
        if job is not None and job.state in ACTIVE:
            raise HTTPException(409, 'Ya hay una solicitud pendiente o en curso. Actualiza su estado.')
        if job is not None and job.state == 'UNCERTAIN' and not payload.confirm_uncertain:
            raise HTTPException(422, 'Confirma que el envío anterior pudo realizarse y que reenviar puede duplicar el correo.')
        problem = configuration_problem(session, event, activation)
        if problem:
            raise HTTPException(422, problem)
        job = request_notification(session, ACTIVATION_EVENT, id, automatic=False, expected_revision=payload.revision)
        message = ('Notificación solicitada. El procesador está pausado; permanecerá pendiente hasta que se autorice su reanudación.'
                   if control.paused else 'Notificación solicitada. El envío se procesará en segundo plano.')
        result = status_response(session, control, activation, event, job, checked=True, message=message)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
