from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.responsible import Responsible
from ticketyn.models.position import Position


class TicketEscalationAck(Base):
    __tablename__ = 'ticket_escalation_acks'
    __table_args__ = (
        CheckConstraint("duration_type IN ('1H', '4H', '8H', 'INDEFINITE')", name='ck_ticket_ack_duration'),
        CheckConstraint("length(btrim(reason)) > 0 AND length(reason) <= 10000", name='ck_ticket_ack_reason'),
        Index('ix_ticket_acks_ticket_id', 'ticket_id'),
        Index('ix_ticket_acks_acknowledged_by_id', 'acknowledged_by_id'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id', ondelete='CASCADE'))
    acknowledged_by_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id', ondelete='RESTRICT'))
    acknowledged_by_position_id: Mapped[int | None] = mapped_column(ForeignKey('positions.id', ondelete='SET NULL'))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    duration_type: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id', ondelete='SET NULL'))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)

    ticket: Mapped['Ticket'] = relationship(back_populates='acks', lazy='raise')
    acknowledged_by: Mapped[Responsible] = relationship(foreign_keys=[acknowledged_by_id], lazy='joined')
    acknowledged_by_position: Mapped[Position | None] = relationship(foreign_keys=[acknowledged_by_position_id], lazy='joined')
    revoked_by: Mapped[Responsible | None] = relationship(foreign_keys=[revoked_by_id], lazy='joined')


Index('uq_ticket_active_ack', TicketEscalationAck.ticket_id, unique=True, postgresql_where=(TicketEscalationAck.active == True))


class InternalTicketEscalationAck(Base):
    __tablename__ = 'internal_ticket_escalation_acks'
    __table_args__ = (
        CheckConstraint("duration_type IN ('1H', '4H', '8H', 'INDEFINITE')", name='ck_internal_ack_duration'),
        CheckConstraint("length(btrim(reason)) > 0 AND length(reason) <= 10000", name='ck_internal_ack_reason'),
        Index('ix_internal_acks_ticket_id', 'ticket_id'),
        Index('ix_internal_acks_acknowledged_by_id', 'acknowledged_by_id'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('internal_tickets.id', ondelete='CASCADE'))
    acknowledged_by_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id', ondelete='RESTRICT'))
    acknowledged_by_position_id: Mapped[int | None] = mapped_column(ForeignKey('positions.id', ondelete='SET NULL'))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    duration_type: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id', ondelete='SET NULL'))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)

    ticket: Mapped['InternalTicket'] = relationship(back_populates='acks', lazy='raise')
    acknowledged_by: Mapped[Responsible] = relationship(foreign_keys=[acknowledged_by_id], lazy='joined')
    acknowledged_by_position: Mapped[Position | None] = relationship(foreign_keys=[acknowledged_by_position_id], lazy='joined')
    revoked_by: Mapped[Responsible | None] = relationship(foreign_keys=[revoked_by_id], lazy='joined')


Index('uq_internal_active_ack', InternalTicketEscalationAck.ticket_id, unique=True, postgresql_where=(InternalTicketEscalationAck.active == True))
