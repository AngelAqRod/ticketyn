"""Provider-specific SMTP OAuth2, with fixed HTTPS endpoints and encrypted state.

No inbox APIs, ID-token login, users, or arbitrary token URLs. Network calls are
isolated so tests can replace them without real accounts.
"""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener
from urllib.error import HTTPError, URLError
import ssl
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from ticketyn.core.config import get_settings
from ticketyn.core.secret_store import get_secret_cipher
from ticketyn.notifications.smtp import MailFailure

CONTEXT = 'mail:transport:1:oauth-credentials'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_SCOPE = 'https://mail.google.com/'
MS_SCOPE = 'https://outlook.office.com/SMTP.Send'
CALLBACK_PATH = '/api/mail-notifications/oauth/callback'
COOKIE_NAME = 'ticketyn_mail_oauth_binding'


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def token_request(url, data):
    """POST only to provider constants; no HTTP debug logging or error bodies."""
    try:
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with opener.open(Request(url, data=urlencode(data).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}), timeout=15) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get('access_token'), str) or not result['access_token'] or len(result['access_token']) > 16384:
            raise ValueError()
        if any(ord(char) < 33 or ord(char) > 126 for char in result['access_token']):
            raise ValueError()
        expires = int(result.get('expires_in', 3600))
        if not 0 < expires <= 86400 or ('token_type' in result and result['token_type'].lower() != 'bearer'):
            raise ValueError()
        refresh = result.get('refresh_token')
        if refresh is not None and (not isinstance(refresh, str) or not 1 <= len(refresh) <= 16384):
            raise ValueError()
        return {'access_token': result['access_token'], 'refresh_token': refresh, 'expires_at': time.time() + expires}
    except HTTPError as error:
        status = error.code
        error.close()
        raise MailFailure('AUTH_ERROR' if status in {400, 401, 403} else 'CONNECTION_ERROR') from None
    except (URLError, OSError, ssl.SSLError):
        raise MailFailure('CONNECTION_ERROR') from None
    except (ValueError, TypeError, AttributeError):
        raise MailFailure('AUTH_ERROR') from None


def read_credentials(row):
    if not row.oauth_credentials_encrypted:
        return {}
    try:
        document = json.loads(get_secret_cipher().decrypt(row.oauth_credentials_encrypted, context=CONTEXT))
        if not isinstance(document, dict): raise ValueError()
        if document.get('binding') != [row.auth_method, row.provider, row.username]:
            raise MailFailure('AUTH_ERROR')
        return document
    except (ValueError, TypeError):
        raise MailFailure('AUTH_ERROR') from None


def save_credentials(row, document):
    document['binding'] = [row.auth_method, row.provider, row.username]
    row.oauth_credentials_encrypted = get_secret_cipher().encrypt(json.dumps(document), context=CONTEXT)


def callback_uri():
    value = get_settings().mail_oauth_redirect_uri
    if not value:
        raise MailFailure('CONFIGURATION_ERROR')
    return value


def provider_endpoints(row):
    if row.provider in {'GMAIL', 'GOOGLE_WORKSPACE'}:
        return 'https://accounts.google.com/o/oauth2/v2/auth', GOOGLE_TOKEN
    tenant = row.oauth_settings.get('tenant_id') or ('consumers' if row.provider == 'OUTLOOK_COM' else None)
    if not tenant:
        raise MailFailure('CONFIGURATION_ERROR')
    return (f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize',
            f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token')


def begin_authorization(row):
    if row.auth_method != 'OAUTH2_DELEGATED' or not row.oauth_settings.get('client_id'):
        raise MailFailure('CONFIGURATION_ERROR')
    document = read_credentials(row)
    if not document.get('client_secret'):
        raise MailFailure('CONFIGURATION_ERROR')
    if document.get('exchange_until', 0) > time.time():
        raise MailFailure('AUTH_ERROR')
    document.pop('tokens', None)
    state, verifier, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    document['pending'] = {'state_hash': digest(state), 'verifier': verifier, 'browser_hash': digest(binding), 'expires_at': time.time() + 600, 'redirect_uri': callback_uri()}
    save_credentials(row, document)
    row.oauth_status = 'REQUIRES_AUTHORIZATION'
    authorize, _ = provider_endpoints(row)
    params = {'client_id': row.oauth_settings['client_id'], 'redirect_uri': callback_uri(), 'response_type': 'code', 'state': state,
              'code_challenge': b64(hashlib.sha256(verifier.encode()).digest()), 'code_challenge_method': 'S256'}
    if row.provider in {'GMAIL', 'GOOGLE_WORKSPACE'}:
        params.update(scope=GOOGLE_SCOPE, access_type='offline', prompt='consent', login_hint=row.username)
    else:
        params.update(scope=MS_SCOPE + ' offline_access', response_mode='query', login_hint=row.username)
    return authorize + '?' + urlencode(params), binding


def consume_authorization(row, state, binding):
    document = read_credentials(row)
    pending = document.get('pending', {})
    if (row.auth_method != 'OAUTH2_DELEGATED' or not state or not binding or not pending
            or pending.get('expires_at', 0) <= time.time()
            or not secrets.compare_digest(pending.get('state_hash', ''), digest(state))
            or not secrets.compare_digest(pending.get('browser_hash', ''), digest(binding))
            or pending.get('redirect_uri') != callback_uri()):
        raise MailFailure('AUTH_ERROR')
    del document['pending']
    document['exchange_id'] = secrets.token_urlsafe(32)
    document['exchange_until'] = time.time() + 600
    row.oauth_status = 'AUTHORIZING'
    save_credentials(row, document)
    return document, pending


def complete_authorization(row, document, pending, code):
    _, token_url = provider_endpoints(row)
    tokens = token_request(token_url, {'grant_type': 'authorization_code', 'client_id': row.oauth_settings['client_id'],
        'client_secret': document['client_secret'], 'code': code, 'redirect_uri': pending['redirect_uri'], 'code_verifier': pending['verifier']})
    # A new authorization must have durable offline access, never reuse an old
    # account's refresh token if a different account was selected at the provider.
    if not tokens.get('refresh_token'):
        raise MailFailure('AUTH_ERROR')
    document.pop('exchange_id', None)
    document.pop('exchange_until', None)
    document['tokens'] = tokens
    save_credentials(row, document)
    row.oauth_status = 'CONNECTED'


def service_assertion(service, username):
    try:
        key = serialization.load_pem_private_key(service['private_key'].encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError()
        now = int(time.time())
        header = b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
        payload = b64(json.dumps({'iss': service['client_email'], 'sub': username, 'aud': GOOGLE_TOKEN, 'scope': GOOGLE_SCOPE, 'iat': now, 'exp': now + 3600}, separators=(',', ':')).encode())
        unsigned = f'{header}.{payload}'
        signature = key.sign(unsigned.encode(), padding.PKCS1v15(), hashes.SHA256())
        return unsigned + '.' + b64(signature)
    except (ValueError, TypeError, KeyError):
        raise MailFailure('CONFIGURATION_ERROR') from None


def access_token(row):
    document = read_credentials(row)
    tokens = document.get('tokens') or {}
    if tokens.get('access_token') and tokens.get('expires_at', 0) > time.time() + 60:
        return tokens['access_token']
    _, url = provider_endpoints(row)
    if row.auth_method == 'OAUTH2_DELEGATED':
        if not tokens.get('refresh_token') or not document.get('client_secret'):
            raise MailFailure('AUTH_ERROR')
        data = {'grant_type': 'refresh_token', 'client_id': row.oauth_settings['client_id'], 'client_secret': document['client_secret'], 'refresh_token': tokens['refresh_token']}
        if row.provider in {'OUTLOOK_COM', 'MICROSOFT_365'}: data['scope'] = MS_SCOPE + ' offline_access'
    elif row.auth_method == 'OAUTH2_APPLICATION' and row.provider == 'GOOGLE_WORKSPACE':
        if not document.get('service_account'):
            raise MailFailure('CONFIGURATION_ERROR')
        data = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': service_assertion(document['service_account'], row.username)}
    elif row.auth_method == 'OAUTH2_APPLICATION' and row.provider == 'MICROSOFT_365':
        if not document.get('client_secret'):
            raise MailFailure('CONFIGURATION_ERROR')
        data = {'grant_type': 'client_credentials', 'client_id': row.oauth_settings['client_id'], 'client_secret': document['client_secret'], 'scope': 'https://outlook.office365.com/.default'}
    else:
        raise MailFailure('CONFIGURATION_ERROR')
    refreshed = token_request(url, data)
    if not refreshed.get('refresh_token') and tokens.get('refresh_token'):
        refreshed['refresh_token'] = tokens['refresh_token']
    document['tokens'] = refreshed
    save_credentials(row, document)
    row.oauth_status = 'CONNECTED'
    return refreshed['access_token']
