"""Read-only audit entries and the exclusive retention setting."""
from typing import Annotated

from fastapi import APIRouter, Query, Request

from ticketyn.api.auth import DB, SafeAuthRoute
from ticketyn.schemas.security_audit import AuditFilters, AuditPage, AuditRetention, AuditRetentionUpdate
from ticketyn.security.audit import audit_page
from ticketyn.security.retention import retention_days, update_retention


router = APIRouter(prefix='/api/security', tags=['security-audit'], route_class=SafeAuthRoute)


@router.get('/audit', response_model=AuditPage)
def list_audit(request: Request, session: DB, filters: Annotated[AuditFilters, Query()]):
    return audit_page(session, request.state.principal, filters)


@router.get('/audit/retention', response_model=AuditRetention)
def get_retention(request: Request, session: DB):
    return {'retention_days': retention_days(session, request.state.principal)}


@router.patch('/audit/retention', response_model=AuditRetention)
def patch_retention(payload: AuditRetentionUpdate, request: Request, session: DB):
    days = update_retention(session, request.state.principal, payload)
    session.commit()
    return {'retention_days': days}
