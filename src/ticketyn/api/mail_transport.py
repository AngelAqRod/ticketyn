"""Explicit administrative SMTP tests and provider authorization; no FMS hooks."""
import json
import logging
from urllib.parse import urlsplit
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from ticketyn.api.crud import DBSession
from ticketyn.api.mail_notifications import router
from ticketyn.core.config import get_settings
from ticketyn.core.secret_store import SecretError
from ticketyn.notifications.delivery import transport_credentials
from ticketyn.notifications import oauth
from ticketyn.notifications.coordination import claim_test, ensure_idle, locked_transport, release_test
from ticketyn.notifications.smtp import TransportSettings, build_message, send_message, MailFailure
from ticketyn.schemas.mail_transport import TestMailRequest, TestMailResponse, OAuthUpdate, OAuthResponse
from ticketyn.schemas.mail_notifications import email_address


class CallbackAccessFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn otherwise logs the complete callback query, including codes.
        return not (isinstance(record.args, tuple) and any(isinstance(arg, str) and arg.split('?', 1)[0] == oauth.CALLBACK_PATH for arg in record.args))


def install_callback_log_filter():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, CallbackAccessFilter) for item in logger.filters):
        logger.addFilter(CallbackAccessFilter())


def oauth_response(row):
    values = row.oauth_settings if row else {}
    return OAuthResponse(client_id=values.get('client_id', ''), tenant_id=values.get('tenant_id', ''),
        redirect_uri=get_settings().mail_oauth_redirect_uri, status=row.oauth_status if row else 'UNCONFIGURED',
        client_secret_configured=values.get('client_secret_configured', False), service_account_configured=values.get('service_account_configured', False))


def require_oauth(row):
    if not row.auth_method.startswith('OAUTH2') or row.security == 'NONE' or not row.provider or not row.username:
        raise HTTPException(422, 'Guarda un perfil OAuth2 con TLS y un buzón SMTP válido.')
    try: email_address(row.username)
    except ValueError:
        raise HTTPException(422, 'El usuario SMTP OAuth2 debe ser una dirección de correo válida.') from None
    if row.auth_method == 'OAUTH2_APPLICATION' and row.provider not in {'GOOGLE_WORKSPACE', 'MICROSOFT_365'}:
        raise HTTPException(422, 'Las cuentas personales no admiten OAuth2 de aplicación.')


@router.get('/oauth', response_model=OAuthResponse)
def get_oauth(session: DBSession):
    from ticketyn.models.mail_notifications import MailTransportConfig
    return oauth_response(session.get(MailTransportConfig, 1))


@router.patch('/oauth', response_model=OAuthResponse)
def update_oauth(payload: OAuthUpdate, session: DBSession):
    try:
        row = locked_transport(session); ensure_idle(row); require_oauth(row)
        values = dict(row.oauth_settings)
        document = oauth.read_credentials(row)
        changes = payload.model_dump(exclude_unset=True, exclude={'client_secret', 'service_account'})
        if changes.get('client_id', values.get('client_id')) != values.get('client_id') and document.get('client_secret') and payload.client_secret is None:
            raise HTTPException(422, 'Al cambiar la aplicación debes proporcionar su nueva credencial.')
        values.update(changes)
        if payload.client_secret is not None:
            if row.provider == 'GOOGLE_WORKSPACE' and row.auth_method == 'OAUTH2_APPLICATION':
                raise HTTPException(422, 'Este perfil utiliza una cuenta de servicio, no un secreto de cliente.')
            document['client_secret'] = payload.client_secret.get_secret_value()
            values['client_secret_configured'] = True
        if payload.service_account is not None:
            if row.provider != 'GOOGLE_WORKSPACE' or row.auth_method != 'OAUTH2_APPLICATION':
                raise HTTPException(422, 'La cuenta de servicio solo corresponde a Google Workspace de aplicación.')
            try:
                service = json.loads(payload.service_account.get_secret_value())
                if service.get('type') != 'service_account': raise ValueError()
                service = {'client_email': email_address(service['client_email']), 'private_key': service['private_key']}
                oauth.service_assertion(service, row.username)  # validates RSA key locally; no network
            except (ValueError, TypeError, KeyError, AttributeError, MailFailure):
                raise HTTPException(422, 'El archivo de cuenta de servicio no es válido.') from None
            document['service_account'] = service
            values['service_account_configured'] = True
        google_service = row.provider == 'GOOGLE_WORKSPACE' and row.auth_method == 'OAUTH2_APPLICATION'
        if not google_service and (not values.get('client_id') or not document.get('client_secret')):
            raise HTTPException(422, 'Completa el identificador y el secreto de la aplicación OAuth2.')
        if google_service and not document.get('service_account'):
            raise HTTPException(422, 'Introduce la cuenta de servicio de Google Workspace.')
        if row.provider == 'MICROSOFT_365' and not values.get('tenant_id'):
            raise HTTPException(422, 'Completa el identificador de tenant de Microsoft 365.')
        if row.provider in {'MICROSOFT_365', 'OUTLOOK_COM'}:
            from uuid import UUID
            try: UUID(values['client_id'])
            except ValueError:
                raise HTTPException(422, 'El identificador de aplicación Microsoft debe ser un UUID.') from None
        if row.provider != 'MICROSOFT_365' and payload.tenant_id is not None:
            raise HTTPException(422, 'El tenant solo se configura para Microsoft 365.')
        if payload.model_fields_set:
            document = {key: value for key, value in document.items() if key in {'binding', 'client_secret', 'service_account'}}
        row.oauth_settings = values
        oauth.save_credentials(row, document)
        if payload.model_fields_set:
            row.oauth_status = 'CONFIGURED' if row.auth_method == 'OAUTH2_APPLICATION' else 'REQUIRES_AUTHORIZATION'
        session.commit()
        return oauth_response(row)
    except Exception:
        session.rollback(); raise


@router.post('/oauth/authorize')
def authorize_oauth(request: Request, session: DBSession):
    try:
        row = locked_transport(session); ensure_idle(row); require_oauth(row)
        url, binding = oauth.begin_authorization(row)
        from ticketyn.security.memory import SessionLimit
        try:
            request.app.state.security.bind_flow(binding, request.state.login_session)
        except SessionLimit:
            raise HTTPException(429, 'Demasiados flujos OAuth2 pendientes') from None
        session.commit()
    except MailFailure as error:
        session.rollback(); raise HTTPException(422, str(error)) from None
    response = Response(content=json.dumps({'authorization_url': url}), media_type='application/json', headers={'Cache-Control': 'no-store'})
    response.set_cookie(oauth.COOKIE_NAME, binding, max_age=600, httponly=True, secure=urlsplit(oauth.callback_uri()).scheme == 'https', samesite='lax', path=oauth.CALLBACK_PATH)
    return response


@router.get('/oauth/callback')
def oauth_callback(request: Request, session: DBSession):
    result = 'error'
    try:
        # Reject duplicate/surplus parameters. Never return provider diagnostics.
        query = request.query_params
        allowed = {'state', 'code', 'error', 'error_description', 'error_uri', 'scope', 'authuser', 'prompt', 'session_state', 'hd', 'error_codes', 'timestamp', 'trace_id', 'correlation_id'}
        if any(key not in allowed or len(query.getlist(key)) != 1 or len(query[key]) > 8192 for key in query):
            raise MailFailure('AUTH_ERROR')
        state = query.get('state', ''); code = query.get('code', '')
        if len(state) > 256 or len(code) > 8192 or (bool(code) == bool(query.get('error'))):
            raise MailFailure('AUTH_ERROR')
        row = locked_transport(session); ensure_idle(row)
        document, pending = oauth.consume_authorization(row, state, request.cookies.get(oauth.COOKIE_NAME, ''))
        exchange_id = document['exchange_id']
        session.commit()  # consume state before any external request, including a crash
        row = locked_transport(session)
        current = oauth.read_credentials(row)
        if current.get('exchange_id') != exchange_id:
            raise MailFailure('AUTH_ERROR')
        try:
            if query.get('error'):
                raise MailFailure('AUTH_ERROR')
            oauth.complete_authorization(row, current, pending, code)
            result = 'connected'
        except MailFailure:
            current.pop('exchange_id', None); current.pop('exchange_until', None); current.pop('tokens', None)
            oauth.save_credentials(row, current)
            row.oauth_status = 'AUTH_ERROR'
        session.commit()
    except (MailFailure, SecretError, HTTPException):
        session.rollback()
    response = RedirectResponse('/mail-notifications?oauth=' + result, status_code=303, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    response.delete_cookie(oauth.COOKIE_NAME, path=oauth.CALLBACK_PATH)
    return response


@router.post('/oauth/disconnect', response_model=OAuthResponse)
def disconnect_oauth(session: DBSession):
    try:
        row = locked_transport(session); ensure_idle(row)
        document = oauth.read_credentials(row)
        document = {key: value for key, value in document.items() if key in {'binding', 'client_secret', 'service_account'}}
        if document.get('client_secret') or document.get('service_account'):
            oauth.save_credentials(row, document)
            row.oauth_status = 'REQUIRES_AUTHORIZATION' if row.auth_method == 'OAUTH2_DELEGATED' else 'CONFIGURED'
        else:
            row.oauth_credentials_encrypted = None; row.oauth_status = 'UNCONFIGURED'
        session.commit()
        return oauth_response(row)
    except Exception:
        session.rollback(); raise


@router.post('/smtp/test', response_model=TestMailResponse)
def test_smtp(payload: TestMailRequest, session: DBSession):
    token = None
    try:
        row, token = claim_test(session)
        if not row.host or not row.sender_email:
            raise MailFailure('CONFIGURATION_ERROR')
        settings = TransportSettings(row.host, row.port, row.security, row.auth_method, row.username, row.allow_unencrypted)
        message, sender, recipients = build_message(sender_email=row.sender_email, sender_name=row.sender_name, to=[payload.recipient],
            subject='Ticketyn — Prueba de correo', body='Este es un correo de prueba del transporte SMTP de Ticketyn. No corresponde a una activación FMS.')
        if row.security == 'NONE' and row.auth_method != 'NONE':
            raise MailFailure('CONFIGURATION_ERROR')
        if row.auth_method.startswith('OAUTH2'):
            require_oauth(row)
        try: credentials = transport_credentials(row)
        except MailFailure as error:
            if error.status == 'AUTH_ERROR': row.oauth_status = 'AUTH_ERROR'
            session.commit()
            raise
        session.commit()  # release DB row lock BEFORE any SMTP commands
        result = send_message(settings, credentials, message, sender, recipients)
        if result.status == 'AUTH_ERROR' and settings.auth_method.startswith('OAUTH2'):
            row = locked_transport(session); row.oauth_status = 'AUTH_ERROR'; session.commit()
        return TestMailResponse(status=result.status, message=result.message)
    except MailFailure as error:
        session.commit()
        return TestMailResponse(status=error.status, message=str(error))
    except SecretError:
        session.rollback(); raise
    finally:
        if token is not None:
            try: release_test(session, token)
            except SQLAlchemyError:
                # Delivery outcome remains known; the lease expires after a crash
                # or failed cleanup. Never retry SMTP to recover database state.
                session.rollback()
