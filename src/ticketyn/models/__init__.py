from ticketyn.models.cpe_model import CpeModel
"""Registro de modelos para SQLAlchemy y Alembic."""

from ticketyn.models.circuit import Circuit
from ticketyn.models.customer import Customer
from ticketyn.models.sector import Sector
from ticketyn.models.department import Department
from ticketyn.models.incident_type import IncidentType
from ticketyn.models.ticket_number_config import TicketNumberConfig
from ticketyn.models.ticket import Ticket
from ticketyn.models.ticket_update import TicketUpdate

from ticketyn.models.node import Node
from ticketyn.models.responsible import Responsible
from ticketyn.models.position import Position

from ticketyn.models.escalation import EscalationReason, TicketEscalation, EscalationAudit

__all__ = ["EscalationAudit", "Position", "EscalationReason", "TicketEscalation", "Customer", "Circuit", "Sector", "Department", "IncidentType", "TicketNumberConfig", "Ticket", "Node", "Responsible", "TicketUpdate"]

from ticketyn.models.fms import Activation, ActivationNumberConfig, ActivationIntervention, CapacityChange, CircuitLifecycleOperation, DeactivationReason

__all__ += ["Activation", "ActivationNumberConfig", "ActivationIntervention", "CapacityChange", "CircuitLifecycleOperation", "DeactivationReason"]

from ticketyn.models.service_type import ServiceType
__all__ += ["ServiceType", "CpeModel"]
