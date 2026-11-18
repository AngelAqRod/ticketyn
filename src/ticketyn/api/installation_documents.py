"""Authenticated private original uploads, metadata, and content."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.distribution_data import distribution_write
from ticketyn.api.installation_orders import router as orders_router, document_data, event, locked
from ticketyn.models.installation_orders import InstallationDocument as Document, InstallationOrder as Order, InstallationRequest as Intake
from ticketyn.incoming.config import IncomingSettings
from ticketyn.incoming.storage import save_document, document_path, storage_lock

router=APIRouter(prefix='/api/installation-documents',tags=['installation-documents'])

def authorized_document(session,id,actor):
    item=get_or_404(session,Document,id)
    allowed=False
    if item.order_id is not None:
        allowed='installation_orders.view' in actor.permissions
    elif 'installation_requests.review' in actor.permissions:
        allowed=True
    elif 'installation_orders.view' in actor.permissions:
        allowed=session.scalar(select(Intake.order_id).where(Intake.id==item.request_id)) is not None
    if not allowed: raise HTTPException(403,'No tienes permiso para consultar este documento.')
    return item

@orders_router.post('/{id}/documents',status_code=201)
async def upload_document(id:int,request:Request,session:DBSession,filename:str):
    limit=IncomingSettings.from_env().max_bytes
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>limit: raise HTTPException(413,'El documento supera el tamaño permitido.')
        content.extend(chunk)
    try:
        with storage_lock(), distribution_write(session):
            locked(session,Order,id)
            document=save_document(session,content=bytes(content),name=filename,order_id=id)
            session.flush()
            event(session,request.state.principal,'DOCUMENT',order_id=id,detail={'document_id':document.id})
            result=document_data(document)
        return result
    except ValueError as error:
        raise HTTPException(422,str(error)) from None
    except OSError:
        raise HTTPException(503,'No se pudo conservar el documento. Reintenta la operación.') from None

@router.get('/{id}')
def metadata(id:int,session:DBSession,request:Request):
    return document_data(authorized_document(session,id,request.state.principal))

@router.get('/{id}/content')
def content(id:int,session:DBSession,request:Request):
    item=authorized_document(session,id,request.state.principal)
    try: path=document_path(item)
    except (ValueError,OSError): raise HTTPException(503,'El documento original no está disponible.') from None
    inline=item.media_type in ('application/pdf','image/png','image/jpeg')
    return FileResponse(path,media_type=item.media_type,filename=item.original_name,content_disposition_type='inline' if inline else 'attachment',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'"})
