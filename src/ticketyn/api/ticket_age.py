"""Antigüedad de tickets abiertos: única definición, usada por el filtro de listado y por el Dashboard.

Antigüedad = ahora (UTC, una sola vez por solicitud) - start_at. No es un SLA.
Tramos excluyentes: <1 h | 1 h ≤ x < 4 h | 4 h ≤ x ≤ 24 h | > 24 h.
Un inicio futuro (antigüedad negativa) no pertenece a ningún tramo y se informa aparte.
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ticketyn.models import Sector, Ticket

AGE_BUCKETS = ("lt_1h", "1_to_4h", "4_to_24h", "gt_24h")
_HOUR = timedelta(hours=1)


def age_condition(bucket: str, now: datetime):
    """Condición SQL (solo sobre start_at) de un tramo; el llamador añade status = 'OPEN'."""
    start = Ticket.start_at
    return {
        "lt_1h": and_(start <= now, start > now - _HOUR),
        "1_to_4h": and_(start <= now - _HOUR, start > now - 4 * _HOUR),
        "4_to_24h": and_(start <= now - 4 * _HOUR, start >= now - 24 * _HOUR),
        "gt_24h": start < now - 24 * _HOUR,
    }[bucket]


def open_overview(session: Session, now: datetime) -> dict:
    """Conteos de abiertos por tramo, sin responsable y por sector; todo con el mismo `now`."""
    is_open = Ticket.status == "OPEN"
    counts = session.execute(select(
        func.count(Ticket.id).filter(is_open).label("open"),
        *(func.count(Ticket.id).filter(is_open, age_condition(bucket, now)).label(bucket) for bucket in AGE_BUCKETS),
        func.count(Ticket.id).filter(is_open, Ticket.start_at > now).label("future_start"),
        func.count(Ticket.id).filter(is_open, Ticket.responsible_id.is_(None)).label("unassigned"),
    )).one()._mapping
    total = func.count(Ticket.id)
    sectors = session.execute(
        select(Sector.id, Sector.name, total.label("count")).join(Sector, Ticket.sector_id == Sector.id)
        .where(is_open).group_by(Sector.id, Sector.name).order_by(total.desc(), Sector.name, Sector.id)
    ).all()
    return {
        "generated_at": now, "open": counts["open"], "future_start": counts["future_start"], "unassigned": counts["unassigned"],
        "buckets": {bucket: counts[bucket] for bucket in AGE_BUCKETS},
        "sectors": [{"id": row.id, "name": row.name, "count": row.count} for row in sectors],
    }
