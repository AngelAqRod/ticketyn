"""Registro de modelos para SQLAlchemy y Alembic."""

from ticketyn.models.circuit import Circuit
from ticketyn.models.customer import Customer
from ticketyn.models.sector import Sector

__all__ = ["Customer", "Circuit", "Sector"]
