"""Phase 2 contracts; full role/account administration screens remain deferred."""
from typing import Annotated
from fastapi import APIRouter, Request, Query, Path, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_, and_
from ticketyn.api.auth import DB, SafeAuthRoute
from ticketyn.models.security import SecurityRole, SecurityRolePermission
from ticketyn.security import roles
from ticketyn.security.permissions import PERMISSIONS

router = APIRouter(prefix='/api/security', tags=['security-roles'], route_class=SafeAuthRoute)
Id = Annotated[int, Path(gt=0)]

class CreateRole(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

class UpdateRole(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    permissions: list[str] | None = Field(default=None, max_length=500)


def output(session, row):
    return {'id': row.id, 'name': row.name, 'description': row.description, 'code': row.code,
            'revision': row.revision, 'permissions': sorted(roles.role_grants(session, row)),
            'editable': row.code is None, 'duplicable': row.code not in {'SUPERADMIN', 'ADMIN'}}


def visible(session, actor, row):
    return 'roles.manage' in actor.permissions or (row.code not in {'SUPERADMIN', 'ADMIN'} and roles.effective_permissions(session, row) < actor.permissions)


@router.get('/permissions')
def permissions():
    return [{'code': p.code, 'module': p.module, 'label': p.label, 'requires': p.requires, 'exclusive': p.exclusive} for p in PERMISSIONS.values()]


@router.get('/roles')
def listing(request: Request, session: DB, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    query = select(SecurityRole)
    actor = request.state.principal
    if 'roles.manage' not in actor.permissions:
        from ticketyn.security.permissions import DEFAULT_GRANTS, expanded_context
        permitted_defaults = [code for code, grants in DEFAULT_GRANTS.items()
                              if code not in {'SUPERADMIN', 'ADMIN'} and expanded_context(grants) < actor.permissions]
        forbidden = select(SecurityRolePermission.role_id).where(
            SecurityRolePermission.role_id == SecurityRole.id,
            SecurityRolePermission.permission_code.not_in(actor.permissions),
        ).exists()
        # A custom role with exactly the manager's grants is an equivalent account.
        # Only roles with strictly fewer effective grants are eligible.
        rows = session.scalars(query.where(or_(SecurityRole.code.in_(permitted_defaults), and_(SecurityRole.code.is_(None), ~forbidden)))
                               .order_by(SecurityRole.name, SecurityRole.id))
        eligible = (row for row in rows if visible(session, actor, row))
        from itertools import islice
        return [output(session, row) for row in islice(eligible, offset, offset + limit)]
    rows = session.scalars(query.order_by(SecurityRole.name, SecurityRole.id).offset(offset).limit(limit))
    return [output(session, row) for row in rows]


@router.get('/roles/{id}')
def detail(id: Id, request: Request, session: DB):
    row = session.get(SecurityRole, id)
    if row is None:
        raise HTTPException(404, 'Rol no encontrado')
    if not visible(session, request.state.principal, row):
        raise HTTPException(403, 'El rol excede tus facultades de administración')
    return output(session, row)


@router.post('/roles', status_code=201)
def create(payload: CreateRole, request: Request, session: DB):
    row = roles.create_role(session, request.state.principal, payload.name, payload.description)
    session.commit()
    return output(session, row)


@router.patch('/roles/{id}')
def update(id: Id, payload: UpdateRole, request: Request, session: DB):
    values = payload.model_dump(exclude_unset=True)
    if any(values.get(key, True) is None for key in ('name', 'permissions')):
        raise HTTPException(422, 'Nombre y permisos no admiten null')
    row = roles.update_role(session, request.state.principal, id, values)
    session.commit()
    return output(session, row)


@router.post('/roles/{id}/duplicate', status_code=201)
def duplicate(id: Id, payload: CreateRole, request: Request, session: DB):
    row = roles.duplicate_role(session, request.state.principal, id, payload.name, payload.description)
    session.commit()
    return output(session, row)


@router.delete('/roles/{id}', status_code=204)
def remove(id: Id, request: Request, session: DB):
    roles.delete_role(session, request.state.principal, id)
    session.commit()
    return Response(status_code=204)
