from enum import Enum


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TicketUpdateVisibility(str, Enum):
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"
