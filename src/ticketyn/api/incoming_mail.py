"""Explicitly authorized intake operations, separate from outbound mail."""
from fastapi import APIRouter, HTTPException, Request
from ticketyn.api.crud import DBSession
from ticketyn.api.distribution_data import distribution_write
from ticketyn.incoming.config import IncomingSettings
from ticketyn.incoming.receiver import reception_filters
from ticketyn.models.installation_orders import InstallationReceptionFilter
from ticketyn.schemas.installation_orders import ReceptionFilterInput

router=APIRouter(prefix='/api/incoming-mail',tags=['incoming-mail'])

@router.get('/status')
def status():
    settings=IncomingSettings.from_env()
    return {'configured':bool(settings.host and settings.username and settings.password),'enabled':settings.enabled,'folder':settings.folder}

@router.post('/poll')
def poll_mail(session:DBSession):
    from ticketyn.incoming.receiver import poll
    try: return poll(session)
    except Exception:
        session.rollback()
        raise HTTPException(503,'No se pudo consultar el correo entrante. Revisa la configuración y los registros del receptor.') from None


@router.get('/filters')
def get_filters(session: DBSession):
    return reception_filters(session)

@router.patch('/filters')
def save_filters(payload: ReceptionFilterInput, session: DBSession, request: Request):
    with distribution_write(session):
        row = session.get(InstallationReceptionFilter, 1)
        if row is None:
            row = InstallationReceptionFilter(id=1)
            session.add(row)
        row.senders, row.subjects, row.updated_by = payload.senders, payload.subjects, request.state.principal.id
        session.flush()
        result = reception_filters(session)
    return result
