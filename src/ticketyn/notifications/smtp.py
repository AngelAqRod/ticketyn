"""Independent MIME builder and bounded SMTP transport. No FMS/database access."""
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.headerregistry import Address as HeaderAddress
from email.policy import SMTP
from email.utils import formatdate, make_msgid
import smtplib
import ssl
from ticketyn.schemas.mail_notifications import email_address

MESSAGES = {
    'ACCEPTED': 'Mensaje aceptado por el servidor SMTP. Esto no garantiza la entrega al buzón.',
    'PARTIAL_ACCEPTED': 'El servidor aceptó algunos destinatarios y rechazó otros. No se reintentó el envío.',
    'CONNECTION_ERROR': 'No se pudo establecer o mantener la conexión con el servidor SMTP.',
    'TLS_ERROR': 'No se pudo establecer una conexión TLS verificada.',
    'AUTH_ERROR': 'La autenticación fue rechazada o requiere nueva autorización.',
    'RECIPIENT_REJECTED': 'El servidor SMTP rechazó el destinatario.',
    'MESSAGE_REJECTED': 'El servidor SMTP rechazó el remitente o el mensaje.',
    'UNCERTAIN': 'Resultado incierto: la conexión se interrumpió durante el envío. Comprueba el buzón antes de repetir la prueba.',
    'CONFIGURATION_ERROR': 'La configuración de correo está incompleta o es incompatible.',
}


class MailFailure(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(MESSAGES[status])


@dataclass(frozen=True)
class SendResult:
    status: str

    @property
    def message(self):
        return MESSAGES[self.status]


@dataclass(frozen=True)
class TransportSettings:
    host: str
    port: int
    security: str
    auth_method: str
    username: str | None = None
    allow_unencrypted: bool = False


@dataclass(frozen=True)
class Credentials:
    password: str | None = field(default=None, repr=False)
    access_token: str | None = field(default=None, repr=False)


def header_text(value):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 or char in '\u2028\u2029' for char in value):
        raise MailFailure('CONFIGURATION_ERROR')
    return value


def build_message(*, sender_email, sender_name, to, cc=(), bcc=(), subject, body, html_body=None):
    """CCO belongs only to the envelope. Content is already safely rendered."""
    try:
        sender = email_address(sender_email)
        local, _, domain = sender.rpartition('@')
        sender = local + '@' + domain.encode('idna').decode('ascii')
        groups = [[email_address(value) for value in group] for group in (to, cc, bcc)]
        groups = [[value.rpartition('@')[0] + '@' + value.rpartition('@')[2].encode('idna').decode('ascii') for value in group] for group in groups]
        envelope, seen = [], set()
        for group in groups:
            for value in group:
                if value.casefold() not in seen:
                    envelope.append(value)
                    seen.add(value.casefold())
        if not envelope or len(envelope) > 300 or len(subject.encode('utf-8')) > 998 or len(body) > 100000:
            raise ValueError()
        message = EmailMessage(policy=SMTP)
        message['From'] = HeaderAddress(display_name=header_text(sender_name), addr_spec=sender)
        if groups[0]: message['To'] = ', '.join(groups[0])
        if groups[1]: message['Cc'] = ', '.join(groups[1])
        message['Subject'] = header_text(subject)
        message['Date'] = formatdate(usegmt=True)
        message['Message-ID'] = make_msgid(domain=sender.rpartition('@')[2])
        message.set_content(body, charset='utf-8')
        if html_body is not None:
            message.add_alternative(html_body, subtype='html', charset='utf-8')
        return message, sender, envelope
    except (ValueError, TypeError, AttributeError):
        raise MailFailure('CONFIGURATION_ERROR') from None


def send_message(settings: TransportSettings, credentials: Credentials, message, sender, recipients):
    if (not settings.host or not 1 <= settings.port <= 65535 or settings.security not in {'NONE', 'STARTTLS', 'IMPLICIT_TLS'}
            or settings.auth_method not in {'NONE', 'PASSWORD', 'OAUTH2_DELEGATED', 'OAUTH2_APPLICATION'}
            or (settings.security == 'NONE' and (not settings.allow_unencrypted or settings.auth_method != 'NONE'))):
        raise MailFailure('CONFIGURATION_ERROR')
    connection = None
    phase = 'connect'
    result = None
    try:
        context = ssl.create_default_context()
        if settings.security == 'IMPLICIT_TLS':
            connection = smtplib.SMTP_SSL(timeout=20, context=context)
        else:
            connection = smtplib.SMTP(timeout=20)
        # Python 3.11's explicit connect() leaves _host unchanged. Both TLS
        # paths use it for certificate hostname verification and SNI. Retain
        # explicit connection/cleanup while setting the actual peer beforehand.
        connection._host = settings.host
        code, _ = connection.connect(settings.host, settings.port)
        if code != 220:
            raise smtplib.SMTPConnectError(code, b'Connection rejected')
        connection.ehlo_or_helo_if_needed()
        if settings.security == 'STARTTLS':
            phase = 'tls'
            if not connection.has_extn('starttls'):
                raise MailFailure('TLS_ERROR')
            connection.starttls(context=context)
            connection.ehlo()
        phase = 'auth'
        if settings.auth_method == 'PASSWORD':
            if not settings.username or not credentials.password:
                raise MailFailure('CONFIGURATION_ERROR')
            connection.login(settings.username, credentials.password)
        elif settings.auth_method.startswith('OAUTH2'):
            if not credentials.access_token or not settings.username:
                raise MailFailure('AUTH_ERROR')
            username = email_address(settings.username)
            header_text(credentials.access_token)
            # smtplib handles SASL base64, including an empty response to an error challenge.
            connection.auth('XOAUTH2', lambda challenge=None: f'user={username}\x01auth=Bearer {credentials.access_token}\x01\x01' if challenge is None else '')
        phase = 'data'
        refused = connection.send_message(message, from_addr=sender, to_addrs=recipients)
        result = SendResult('PARTIAL_ACCEPTED' if refused else 'ACCEPTED')
    except MailFailure:
        raise
    except smtplib.SMTPAuthenticationError:
        result = SendResult('AUTH_ERROR')
    except smtplib.SMTPNotSupportedError:
        result = SendResult('AUTH_ERROR' if phase == 'auth' else 'TLS_ERROR' if phase == 'tls' else 'CONNECTION_ERROR')
    except smtplib.SMTPRecipientsRefused:
        result = SendResult('RECIPIENT_REJECTED')
    except (smtplib.SMTPDataError, smtplib.SMTPSenderRefused):
        result = SendResult('MESSAGE_REJECTED')
    except ssl.SSLError:
        result = SendResult('UNCERTAIN' if phase == 'data' else 'TLS_ERROR')
    except smtplib.SMTPResponseException:
        result = SendResult('AUTH_ERROR' if phase == 'auth' else 'MESSAGE_REJECTED' if phase == 'data' else 'TLS_ERROR' if phase == 'tls' else 'CONNECTION_ERROR')
    except (OSError, smtplib.SMTPException):
        result = SendResult('UNCERTAIN' if phase == 'data' else 'TLS_ERROR' if phase == 'tls' else 'CONNECTION_ERROR')
    except (ValueError, UnicodeError):
        result = SendResult('CONFIGURATION_ERROR')
    finally:
        if connection is not None:
            if result and result.status in {'ACCEPTED', 'PARTIAL_ACCEPTED'}:
                try: connection.quit()
                except (OSError, smtplib.SMTPException): pass
            try: connection.close()
            except (OSError, smtplib.SMTPException): pass
    return result
