from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from ticketyn.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    """Sesión por petición; el consumidor controla commit y rollback."""
    with Session(get_engine()) as session:
        yield session
