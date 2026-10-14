from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from ticketyn.schemas.report import ReportFilters, ReportPeriod, ReportRanking
from ticketyn.schemas.common import AssignmentSummary


class FmsReportFilters(ReportFilters):
    timezone: str = Field(default='America/Guatemala', max_length=100)
    granularity: Literal['auto', 'day', 'month'] = 'auto'
    recipient_id: None = None


class FmsReportDetailFilters(FmsReportFilters):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ActivationKpis(BaseModel):
    total: int
    distinct_customers: int
    distinct_circuits: int


class CapacityKpis(BaseModel):
    increases: int
    decreases: int
    known_added_mbps: Decimal
    known_reduced_mbps: Decimal
    known_net_mbps: Decimal
    unknown_variations: int


class LifecycleKpis(BaseModel):
    deactivations: int
    reactivations: int
    distinct_deactivated_circuits: int
    distinct_reactivated_circuits: int


class FmsTrendBucket(BaseModel):
    start_at: datetime
    count: int
    first: int
    second: int


class FmsReportSummary(BaseModel):
    generated_at: datetime
    period: ReportPeriod
    sector: AssignmentSummary | None
    node: AssignmentSummary | None
    responsible: AssignmentSummary | None
    kpis: ActivationKpis | CapacityKpis | LifecycleKpis
    trend: list[FmsTrendBucket]
    customers: list[ReportRanking]
    reasons: list[ReportRanking]
