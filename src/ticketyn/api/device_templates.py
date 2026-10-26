"""Reusable definitions, never synchronization of installed devices."""
import hashlib
import json
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.distribution_data import distribution_write, locked, record, snapshot
from ticketyn.api.port_nomenclatures import generated_names, normalized_port_names, insert_ports
from ticketyn.models import DistributionDeviceTemplate, DistributionDeviceTemplateGroup, PortNomenclature
from ticketyn.schemas.device_template import TemplateInput, TemplatePreview, TemplateResponse, TemplateGroup

router = APIRouter(prefix='/api/distribution-device-templates', tags=['device-templates'])


def definition(item):
    return [TemplateGroup(nomenclature_id=g.nomenclature_id, **g.definition) for g in item.groups]


def check_definition(session, groups, *, previous=()):
    catalogs = {row.id: row for row in session.scalars(select(PortNomenclature).where(
        PortNomenclature.id.in_({g.nomenclature_id for g in groups})).with_for_update(read=True))}
    result, all_names = [], []
    allowed = [g.model_dump() for g in previous]
    for index, group in enumerate(groups, 1):
        catalog = catalogs.get(group.nomenclature_id)
        if catalog is None:
            raise HTTPException(422, f'Grupo {index}: la nomenclatura no existe')
        warning = None
        if not catalog.active or group.numbering_format not in catalog.formats:
            warning = f'Grupo {index}: nomenclatura o formato no habilitados'
            if group.model_dump() not in allowed:
                raise HTTPException(422, warning)
        names = generated_names(catalog.prefix, group.numbering_format, group.positions, group.start, group.end)
        all_names.extend((name, index) for name in names)
        result.append(dict(**group.model_dump(), nomenclature_name=catalog.name, prefix=catalog.prefix,
                           names=names, warning=warning))
    if len(all_names) > 256:
        raise HTTPException(422, 'La plantilla completa admite como máximo 256 puertos')
    seen = {}
    for (name, index), key in zip(all_names, normalized_port_names(session, [n for n, _ in all_names])):
        if key in seen:
            raise HTTPException(422, f'Nombre duplicado {name}: grupos {seen[key]} y {index}')
        seen[key] = index
    token = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(groups=result, total_ports=len(all_names), usable=not any(g['warning'] for g in result), preview_token=token)


def view(session, item):
    groups = definition(item)
    checked = check_definition(session, groups, previous=groups)
    return TemplateResponse(id=item.id, name=item.name, manufacturer=item.manufacturer,
                            description=item.description, active=item.active, created_at=item.created_at,
                            **{**checked, 'usable': item.active and checked['usable']})


@router.get('', response_model=list[TemplateResponse])
def list_templates(session: DBSession, include_inactive: bool = False,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    query = select(DistributionDeviceTemplate)
    if not include_inactive:
        query = query.where(DistributionDeviceTemplate.active.is_(True))
    return [view(session, item) for item in session.scalars(query.order_by(
        DistributionDeviceTemplate.name, DistributionDeviceTemplate.id).limit(limit).offset(offset)).all()]


@router.post('/preview', response_model=TemplatePreview)
def preview_template(payload: TemplateInput, session: DBSession, template_id: int | None = None):
    previous = definition(get_or_404(session, DistributionDeviceTemplate, template_id)) if template_id else []
    return check_definition(session, payload.groups, previous=previous)


@router.get('/{id}', response_model=TemplateResponse)
@router.get('/{id}/preview', response_model=TemplateResponse)
def get_template(id: int, session: DBSession):
    return view(session, get_or_404(session, DistributionDeviceTemplate, id))


def save_template(session, request, payload, item=None):
    with distribution_write(session):
        if item is not None:
            item = locked(session, DistributionDeviceTemplate, item)
        before = snapshot(item) if item else None
        old_groups = definition(item) if item else []
        # Inactive historical definitions may remain unchanged; reactivation must be valid.
        previous = old_groups if item and (item.active or not payload.active) else []
        checked = check_definition(session, payload.groups, previous=previous)
        if payload.preview_token != checked['preview_token']:
            raise HTTPException(409, 'La definición cambió. Comprueba nuevamente la vista previa')
        if item is None:
            item = DistributionDeviceTemplate()
            session.add(item)
        else:
            item.groups.clear()
            session.flush()
        for key, value in payload.model_dump(exclude={'groups', 'preview_token'}).items():
            setattr(item, key, value)
        item.groups = [DistributionDeviceTemplateGroup(position=index, nomenclature_id=g.nomenclature_id,
                       definition=g.model_dump(exclude={'nomenclature_id'})) for index, g in enumerate(payload.groups)]
        session.flush()
        record(session, request.state.principal.id, item, 'EDIT' if before else 'CREATE', before)
        result = view(session, item)
    return result


@router.post('', response_model=TemplateResponse, status_code=201)
def create_template(payload: TemplateInput, session: DBSession, request: Request):
    return save_template(session, request, payload)


@router.patch('/{id}', response_model=TemplateResponse)
def update_template(id: int, payload: TemplateInput, session: DBSession, request: Request):
    return save_template(session, request, payload, id)


def apply_template(session, template_id, token, device, actor_id):
    item = locked(session, DistributionDeviceTemplate, template_id)
    checked = view(session, item)
    if not checked.usable:
        raise HTTPException(422, 'La plantilla está inactiva o utiliza nomenclaturas o formatos no habilitados')
    if token != checked.preview_token:
        raise HTTPException(409, 'La plantilla cambió. Comprueba nuevamente sus grupos antes de crear el equipo')
    rows = [dict(name=name, nomenclature_id=group.nomenclature_id, numbering_format=group.numbering_format,
                 number_components=[*group.positions, number], description=None)
            for group in checked.groups for number, name in enumerate(group.names, group.start)]
    insert_ports(session, actor_id, device.id, rows)
