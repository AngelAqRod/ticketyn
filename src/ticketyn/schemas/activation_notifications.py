"""Operator contracts: current technical state and explicit manual intent only."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from ticketyn.schemas.mail_notifications import Mode

NotificationState = Literal['PENDING', 'PREPARING', 'SENDING', 'ACCEPTED', 'FAILED', 'PARTIAL', 'UNCERTAIN', 'CANCELLED']


class RequestActivationNotification(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=0)
    confirm_uncertain: bool = False


class ActivationNotificationStatus(BaseModel):
    activation_id: int
    mode: Mode
    state: NotificationState | None
    revision: int
    processor_paused: bool
    can_request: bool
    configuration_error: str | None = None
    message: str | None = None
