from sqlalchemy import Index, func
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields
from ticketyn.models.responsible import Responsible


class EscalationReason(CommonFields, Base):
    __tablename__ = 'escalation_reasons'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class TicketEscalation(Base):
    __tablename__ = 'ticket_escalations'
    __table_args__ = (
        UniqueConstraint("id", "ticket_id", name="uq_ticket_escalations_id_ticket_id"),
        CheckConstraint("status IN ('ACTIVE', 'FINISHED')", name='status_values'),
        CheckConstraint("(status = 'ACTIVE' AND finished_at IS NULL) OR (status = 'FINISHED' AND finished_at IS NOT NULL AND finished_at >= created_at)", name='finish_consistency'),
        CheckConstraint('length(btrim(description)) > 0 AND length(description) <= 10000', name='description_content'),
        Index('ix_ticket_escalations_ticket_chronology', 'ticket_id', 'created_at', 'id'),
        Index('ix_ticket_escalations_created_at', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    requester_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), index=True)
    recipient_level: Mapped[str | None] = mapped_column(String(100))
    recipient_position_name: Mapped[str | None] = mapped_column(String(100))
    recipient_department_name: Mapped[str | None] = mapped_column(Text)
    reason_id: Mapped[int] = mapped_column(ForeignKey('escalation_reasons.id'), index=True)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8), server_default='ACTIVE')
    ticket: Mapped['Ticket'] = relationship(back_populates='escalations', lazy='raise')
    requester: Mapped[Responsible | None] = relationship(foreign_keys=[requester_id], lazy='joined')
    recipient: Mapped[Responsible] = relationship(foreign_keys=[recipient_id], lazy='joined')
    reason: Mapped[EscalationReason] = relationship(lazy='joined')


Index('uq_escalation_reasons_name_normalized', func.lower(func.btrim(EscalationReason.name).collate('C.utf8')), unique=True)
