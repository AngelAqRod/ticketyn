from enum import Enum


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
