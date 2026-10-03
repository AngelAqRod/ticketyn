from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Node
from ticketyn.schemas.node import NodeCreate, NodeResponse, NodeUpdate

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.post("", response_model=NodeResponse, status_code=201)
def create_node(payload: NodeCreate, session: DBSession):
    return save_item(session, Node(**payload.model_dump()))


@router.get("", response_model=list[NodeResponse])
def list_nodes(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Node, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=NodeResponse)
def get_node(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Node, id)


@router.patch("/{id}", response_model=NodeResponse)
def patch_node(id: Annotated[int, Path(gt=0)], payload: NodeUpdate, session: DBSession):
    item = get_or_404(session, Node, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
