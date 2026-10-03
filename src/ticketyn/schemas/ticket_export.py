from pydantic import Field, field_validator

from ticketyn.schemas.report import ReportFilters
from ticketyn.schemas.ticket import TicketFilters


class TicketExportFilters(TicketFilters):
    timezone: str = Field(default='UTC', max_length=100, description='Zona IANA para presentar fechas; no cambia los filtros')

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        return ReportFilters.valid_timezone(value)
