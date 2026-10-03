from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from ticketyn.schemas.ticket import PositiveId


class ReportFilters(BaseModel):
    from_at: AwareDatetime = Field(alias='from', description='Inicio inclusivo del período; timestamp con zona horaria')
    to_at: AwareDatetime = Field(alias='to', description='Fin exclusivo del período; timestamp con zona horaria')
    sector_id: PositiveId | None = None
    node_id: PositiveId | None = None
    responsible_id: PositiveId | None = None
    timezone: str = Field(default='UTC', max_length=100, description='Zona IANA para agrupar y presentar; la UI envía la zona del navegador')
    granularity: Literal['auto', 'hour', 'day', 'week', 'month'] = 'auto'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Zona horaria IANA inválida') from None
        return value

    @model_validator(mode='after')
    def valid_period(self):
        seconds = (self.to_at - self.from_at).total_seconds()
        if seconds <= 0 or seconds > 3660 * 86400:
            raise ValueError('El período debe ser positivo y no superar diez años')
        if self.granularity == 'hour' and seconds > 400 * 3600:
            raise ValueError('Demasiados puntos por hora; utiliza otra granularidad')
        if self.granularity == 'day' and seconds > 400 * 86400:
            raise ValueError('Demasiados puntos por día; utiliza otra granularidad')
        if self.granularity == 'week' and seconds > 400 * 7 * 86400:
            raise ValueError('Demasiados puntos por semana; utiliza otra granularidad')
        return self

    def ticket_filters(self):
        return {'from_at': self.from_at, 'to_at': self.to_at, 'sector_id': self.sector_id, 'node_id': self.node_id, 'responsible_id': self.responsible_id}


class ReportPeriod(BaseModel):
    from_at: datetime
    to_exclusive: datetime
    timezone: str
    granularity: str


class ReportKpis(BaseModel):
    started: int
    closed: int
    average_duration_seconds: float | None
    total_duration_seconds: float


class TrendBucket(BaseModel):
    start_at: datetime
    count: int


class ReportRanking(BaseModel):
    id: int
    label: str
    count: int
    customer_id: int | None = None
    customer_code: str | None = None
    customer_name: str | None = None


class ActivityBucket(BaseModel):
    start_at: datetime
    started: int
    closed: int


class SectorDuration(BaseModel):
    id: int
    label: str
    count: int
    average_duration_seconds: float


class ReportSummary(BaseModel):
    node: dict[str, str | int] | None = None
    responsible: dict[str, str | int] | None = None
    nodes: list[ReportRanking] = Field(default_factory=list)
    responsibles: list[ReportRanking] = Field(default_factory=list)
    activity: list[ActivityBucket] = Field(default_factory=list)
    hours: list[ReportRanking] = Field(default_factory=list)
    weekdays: list[ReportRanking] = Field(default_factory=list)
    sector_durations: list[SectorDuration] = Field(default_factory=list)
    period: ReportPeriod
    generated_at: datetime
    sector: dict[str, str | int] | None
    kpis: ReportKpis
    trend: list[TrendBucket]
    sectors: list[ReportRanking]
    customers: list[ReportRanking]
    circuits: list[ReportRanking]
    incident_types: list[ReportRanking]
