from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class MyTicketItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_type: Literal['CUSTOMER', 'INTERNAL']
    reference: str
    title: str
    description: str
    status: Literal['OPEN', 'CLOSED']
    created_at: datetime
    start_at: datetime
    end_at: datetime | None = None

    # Responsible info
    responsible_id: int | None = None
    responsible_name: str | None = None

    # Location / classification
    sector_name: str | None = None
    node_name: str | None = None
    department_name: str | None = None
    incident_type_name: str | None = None

    # Customer specific
    customer_name: str | None = None
    customer_code: str | None = None
    circuit_code: str | None = None

    # Internal ticket specific
    provider_name: str | None = None

    # Recommendation indicator
    has_recommendation: bool = False
    recommendations_count: int = 0

    # Escalation details (for 'escalations' view)
    escalation_id: int | None = None
    escalation_status: str | None = None
    escalation_reason: str | None = None
    escalation_started_at: datetime | None = None
    escalation_finished_at: datetime | None = None
    escalation_description: str | None = None
    escalation_requester_name: str | None = None
    escalation_recipient_name: str | None = None
    escalation_position_name: str | None = None

    # Verification / recommendation details (for 'to_verify' view)
    recommendation_stage: str | None = None
    recommendation_elapsed_minutes: int | None = None
    recommendation_threshold_minutes: int | None = None
    recommendation_overdue_minutes: int | None = None
    recommendation_target_position_name: str | None = None
    recommendation_reference_position_name: str | None = None


class MyTicketsListResponse(BaseModel):
    items: list[MyTicketItem]
    total: int
    limit: int
    offset: int


class MyTicketsSummaryResponse(BaseModel):
    assigned_count: int
    participated_count: int
    escalations_count: int
    to_verify_count: int
