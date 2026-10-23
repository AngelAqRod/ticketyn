"""One generator for individual creation, previews and transactional ranges."""
import hashlib
import json
from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select, text
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.distribution_data import distribution_write, active_device, locked, snapshot, record
from ticketyn.models import DistributionPort, PortNomenclature
from ticketyn.models.distribution import normalized_name
from ticketyn.schemas.port_nomenclature import NomenclatureInput, NomenclatureResponse, PortGeneration, PortPreview, PortBatchResponse

router = APIRouter(prefix='/api', tags=['port-nomenclatures'])


def generated_names(prefix, numbering_format, positions, start, end):
    if numbering_format not in ('N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z') or len(positions) != numbering_format.count('/'):
        raise HTTPException(422, 'Formato o posiciones no válidos')
    if end < start or end - start + 1 > 256 or any(type(n) is not int or n < 0 for n in [*positions, start, end]):
        raise HTTPException(422, 'Solicita entre 1 y 256 nombres con números enteros no negativos')
    names = [prefix + '/'.join(map(str, [*positions, n])) for n in range(start, end + 1)]
    if any(len(name) > 255 for name in names):
        raise HTTPException(422, 'El nombre generado supera 255 caracteres')
    return names


@router.get('/port-nomenclatures', response_model=list[NomenclatureResponse])
def list_nomenclatures(session: DBSession, include_inactive: bool = False,
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    query = select(PortNomenclature)
    if not include_inactive: query = query.where(PortNomenclature.active.is_(True))
    return session.scalars(query.order_by(PortNomenclature.name, PortNomenclature.id).limit(limit).offset(offset)).all()


@router.get('/port-nomenclatures/{id}', response_model=NomenclatureResponse)
def get_nomenclature(id: int, session: DBSession):
    return get_or_404(session, PortNomenclature, id)


@router.post('/port-nomenclatures', response_model=NomenclatureResponse, status_code=201)
def create_nomenclature(payload: NomenclatureInput, session: DBSession, request: Request):
    with distribution_write(session):
        item = PortNomenclature(**payload.model_dump()); session.add(item); session.flush()
        record(session, request.state.principal.id, item, 'CREATE')
        result = NomenclatureResponse.model_validate(item)
    return result


@router.patch('/port-nomenclatures/{id}', response_model=NomenclatureResponse)
def edit_nomenclature(id: int, payload: NomenclatureInput, session: DBSession, request: Request):
    with distribution_write(session):
        item = locked(session, PortNomenclature, id); before = snapshot(item)
        if payload.prefix != item.prefix and session.scalar(select(DistributionPort.id).where(DistributionPort.nomenclature_id == id).limit(1)):
            raise HTTPException(409, 'No se puede cambiar el prefijo: tiene puertos asociados')
        for key, value in payload.model_dump().items(): setattr(item, key, value)
        session.flush(); record(session, request.state.principal.id, item, 'EDIT', before)
        result = NomenclatureResponse.model_validate(item)
    return result


@router.delete('/port-nomenclatures/{id}', status_code=204)
def delete_nomenclature(id: int, session: DBSession, request: Request):
    with distribution_write(session):
        item = locked(session, PortNomenclature, id)
        if session.scalar(select(DistributionPort.id).where(DistributionPort.nomenclature_id == id).limit(1)):
            raise HTTPException(409, 'La nomenclatura tiene puertos asociados; puedes desactivarla')
        record(session, request.state.principal.id, item, 'DELETE', snapshot(item), deleted=True)
        session.delete(item); session.flush()
    return Response(status_code=204)


def preview(session, payload):
    device = active_device(session, payload.distribution_device_id)
    nomenclature = get_or_404(session, PortNomenclature, payload.nomenclature_id)
    if not nomenclature.active or payload.numbering_format not in nomenclature.formats:
        raise HTTPException(422, 'La nomenclatura o el formato ya no están habilitados; vuelve a comprobar')
    names = generated_names(nomenclature.prefix, payload.numbering_format, payload.positions,
                            payload.start, payload.start if payload.end is None else payload.end)
    # Use exactly the DB index expression, including its Unicode collation and whitespace rules.
    keys = list(session.scalars(text("SELECT lower(btrim(regexp_replace(value, '[[:space:]]+', ' ', 'g')) COLLATE \"C.utf8\") FROM unnest(CAST(:names AS text[])) AS value"), {'names': names}))
    existing = session.execute(select(DistributionPort.id, DistributionPort.name, DistributionPort.active,
        normalized_name(DistributionPort.name).label('key')).where(DistributionPort.distribution_device_id == payload.distribution_device_id,
        normalized_name(DistributionPort.name).in_(keys))).mappings().all()
    by_key = {row['key']: row for row in existing}
    items = [{'name': name, 'existing': key in by_key} for name, key in zip(names, keys)]
    signature = {'request': payload.model_dump(exclude={'preview_token'}),
        'device': [device.id, device.node_id, device.name, device.active],
        'catalog': [nomenclature.id, nomenclature.name, nomenclature.prefix, nomenclature.formats],
        'existing': sorted((row['id'], row['name'], row['active']) for row in existing)}
    token = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    count = sum(item['existing'] for item in items)
    return {'names': items, 'total': len(names), 'existing_count': count,
            'create_count': len(names) - count, 'preview_token': token,
            'blocked': payload.mode == 'complete' and count > 0}


@router.post('/distribution-ports/preview', response_model=PortPreview)
def preview_ports(payload: PortGeneration, session: DBSession):
    return preview(session, payload)


@router.post('/distribution-ports/batch', response_model=PortBatchResponse)
def create_ports(payload: PortGeneration, session: DBSession, request: Request):
    from ticketyn.api.distribution import port_response
    with distribution_write(session):
        checked = preview(session, payload)
        if payload.preview_token != checked['preview_token']:
            raise HTTPException(409, 'La información cambió o falta comprobación. Revisa una nueva vista previa antes de crear')
        if checked['blocked']:
            raise HTTPException(409, 'El rango contiene puertos existentes; no se creó ningún puerto')
        if checked['create_count'] == 0:
            return {'created': [], 'existing_count': checked['existing_count'], 'total': checked['total']}
        created = []
        for number, item in enumerate(checked['names'], payload.start):
            if item['existing']: continue
            port = DistributionPort(distribution_device_id=payload.distribution_device_id,
                nomenclature_id=payload.nomenclature_id, numbering_format=payload.numbering_format,
                number_components=[*payload.positions, number], name=item['name'], description=payload.description, active=True)
            session.add(port); created.append(port)
        session.flush()
        for port in created:
            record(session, request.state.principal.id, port, 'CREATE', flush=False)
        session.flush()
        result = {'created': [port_response((port, 0)) for port in created], 'existing_count': checked['existing_count'], 'total': checked['total']}
    return result


def validate_port_edit(session, item, values):
    meta = ('nomenclature_id', 'numbering_format', 'number_components')
    if any(field in values for field in meta):
        if not all(field in values for field in meta):
            raise HTTPException(422, 'Envía la clasificación completa o sus tres valores null para retirarla')
        if all(values[field] is None for field in meta):
            return
        if any(values[field] is None for field in meta):
            raise HTTPException(422, 'La clasificación debe estar completa')
        catalog = get_or_404(session, PortNomenclature, values['nomenclature_id'])
        components = values['number_components']
        if not catalog.active or values['numbering_format'] not in catalog.formats:
            raise HTTPException(422, 'Nomenclatura o formato no habilitados')
        name = generated_names(catalog.prefix, values['numbering_format'], components[:-1], components[-1], components[-1])[0]
        original = values.get('name', item.name)
        if original.casefold() != name.casefold():
            raise HTTPException(422, 'La clasificación debe coincidir con el nombre; no se renombra automáticamente')
    elif item.nomenclature_id is not None and values.get('name', item.name) != item.name:
        raise HTTPException(422, 'El nombre clasificado se genera desde su nomenclatura. Conserva el nombre o envía una clasificación completa válida.')
