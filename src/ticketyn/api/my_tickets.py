from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request

from ticketyn.api import my_tickets_data
from ticketyn.api.crud import DBSession
from ticketyn.schemas.my_tickets import (
    MyTicketsListResponse,
    MyTicketsSummaryResponse,
)

router = APIRouter(prefix="/api/my-tickets", tags=["my-tickets"])


@router.get("/summary", response_model=MyTicketsSummaryResponse)
def my_tickets_summary(request: Request, session: DBSession):
    return my_tickets_data.get_my_tickets_summary(session, request.state.principal)


@router.get("", response_model=MyTicketsListResponse)
def list_my_tickets(
    request: Request,
    session: DBSession,
    view: Literal['assigned', 'participated', 'escalations', 'to_verify'] = 'assigned',
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    status: Literal['ALL', 'OPEN', 'CLOSED'] | None = None,
    escalation_status: Literal['ALL', 'ACTIVE', 'FINISHED'] | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    actor = request.state.principal
    if view == 'assigned':
        st = status if status is not None else 'OPEN'
        return my_tickets_data.get_assigned_tickets(
            session, actor, scope=scope, status=st, search=search, limit=limit, offset=offset
        )
    elif view == 'participated':
        st = status if status is not None else 'OPEN'
        return my_tickets_data.get_participated_tickets(
            session, actor, scope=scope, status=st, search=search, limit=limit, offset=offset
        )
    elif view == 'escalations':
        esc_st = escalation_status if escalation_status is not None else 'ACTIVE'
        return my_tickets_data.get_my_escalations(
            session, actor, scope=scope, escalation_status=esc_st, search=search, limit=limit, offset=offset
        )
    elif view == 'to_verify':
        return my_tickets_data.get_to_verify_tickets(
            session, actor, scope=scope, search=search, limit=limit, offset=offset
        )
    else:
        raise HTTPException(400, f"Vista desconocida: {view}")


@router.get("/assigned", response_model=MyTicketsListResponse)
def list_assigned(
    request: Request,
    session: DBSession,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    status: Literal['ALL', 'OPEN', 'CLOSED'] = 'OPEN',
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return my_tickets_data.get_assigned_tickets(
        session, request.state.principal, scope=scope, status=status, search=search, limit=limit, offset=offset
    )


@router.get("/participated", response_model=MyTicketsListResponse)
def list_participated(
    request: Request,
    session: DBSession,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    status: Literal['ALL', 'OPEN', 'CLOSED'] = 'OPEN',
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return my_tickets_data.get_participated_tickets(
        session, request.state.principal, scope=scope, status=status, search=search, limit=limit, offset=offset
    )


@router.get("/escalations", response_model=MyTicketsListResponse)
def list_escalations(
    request: Request,
    session: DBSession,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    escalation_status: Literal['ALL', 'ACTIVE', 'FINISHED'] = 'ACTIVE',
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return my_tickets_data.get_my_escalations(
        session,
        request.state.principal,
        scope=scope,
        escalation_status=escalation_status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/to-verify", response_model=MyTicketsListResponse)
def list_to_verify(
    request: Request,
    session: DBSession,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return my_tickets_data.get_to_verify_tickets(
        session, request.state.principal, scope=scope, search=search, limit=limit, offset=offset
    )
