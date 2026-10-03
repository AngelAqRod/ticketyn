"""Registro de modelos para SQLAlchemy y Alembic."""

from ticketyn.models.circuit import Circuit
from ticketyn.models.customer import Customer
from ticketyn.models.sector import Sector
from ticketyn.models.department import Department
from ticketyn.models.incident_type import IncidentType
from ticketyn.models.ticket_number_config import TicketNumberConfig
from ticketyn.models.ticket import Ticket

from ticketyn.models.node import Node
from ticketyn.models.responsible import Responsible

__all__ = ["Customer", "Circuit", "Sector", "Department", "IncidentType", "TicketNumberConfig", "Ticket", "Node", "Responsible"]
