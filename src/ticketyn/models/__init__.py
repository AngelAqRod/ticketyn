"""Registro de modelos para SQLAlchemy y Alembic."""

from ticketyn.models.circuit import Circuit
from ticketyn.models.customer import Customer
from ticketyn.models.sector import Sector
from ticketyn.models.service import Service

__all__ = ["Customer", "Circuit", "Service", "Sector"]
