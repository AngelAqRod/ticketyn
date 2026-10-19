"""Shared transport preparation for explicit tests and persistent requests."""
from ticketyn.core.secret_store import get_secret_cipher
from ticketyn.notifications import oauth
from ticketyn.notifications.smtp import Credentials, MailFailure, TransportSettings

PASSWORD_CONTEXT = 'mail:transport:1:smtp-password'


def transport_settings(row):
    if not row.host or not row.sender_email or (row.security == 'NONE' and row.auth_method != 'NONE'):
        raise MailFailure('CONFIGURATION_ERROR')
    return TransportSettings(row.host, row.port, row.security, row.auth_method, row.username, row.allow_unencrypted)


def transport_credentials(row):
    if row.auth_method == 'PASSWORD':
        if not row.smtp_password_encrypted: raise MailFailure('CONFIGURATION_ERROR')
        return Credentials(password=get_secret_cipher().decrypt(row.smtp_password_encrypted, context=PASSWORD_CONTEXT))
    if row.auth_method.startswith('OAUTH2'):
        return Credentials(access_token=oauth.access_token(row))
    return Credentials()
