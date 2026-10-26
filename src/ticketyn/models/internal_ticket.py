"""Infrastructure tickets: no customer/circuit or customer-facing content."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields
from ticketyn.models.responsible import Responsible
from ticketyn.models.position import Position
from ticketyn.models.escalation import EscalationReason

class InternalIncidentType(CommonFields, Base):
    __tablename__ = 'internal_incident_types'
    name: Mapped[str] = mapped_column(String, unique=True)

class Provider(CommonFields, Base):
    __tablename__ = 'providers'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

for model in (InternalIncidentType, Provider):
    Index(f'uq_{model.__tablename__}_name_normalized', func.lower(func.btrim(model.name).collate('C.utf8')), unique=True)

class InternalTicketNumberConfig(Base):
    __tablename__ = 'internal_ticket_number_config'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'), CheckConstraint('next_number > 0', name='positive_next_number'), CheckConstraint('padding >= 0', name='nonnegative_padding'))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    prefix: Mapped[str] = mapped_column(String, server_default=text("'INT'"))
    separator: Mapped[str] = mapped_column(String, server_default=text("'-'"))
    next_number: Mapped[int] = mapped_column(server_default=text('1'))
    padding: Mapped[int] = mapped_column(server_default=text('7'))

class InternalTicket(Base):
    __tablename__ = 'internal_tickets'
    __table_args__ = (CheckConstraint('ticket_number > 0', name='positive_ticket_number'), CheckConstraint("status IN ('OPEN', 'CLOSED')", name='status_values'), CheckConstraint('end_at IS NULL OR end_at >= start_at', name='valid_dates'), CheckConstraint('resolution IS NULL OR (length(btrim(resolution)) > 0 AND length(resolution) <= 10000)', name='resolution_content'))
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(unique=True)
    reference: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    sector_id: Mapped[int] = mapped_column(ForeignKey('sectors.id'), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey('nodes.id'), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), index=True)
    incident_type_id: Mapped[int] = mapped_column(ForeignKey('internal_incident_types.id'), index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey('providers.id'), index=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'), index=True)
    initial_position_id: Mapped[int | None] = mapped_column(ForeignKey('positions.id', ondelete='SET NULL'), index=True)
    closed_seconds: Mapped[int] = mapped_column(server_default=text('0'))
    responsible: Mapped[Responsible | None] = relationship(lazy='joined')
    initial_position: Mapped[Position | None] = relationship(foreign_keys=[initial_position_id], lazy='joined')
    sector: Mapped['Sector'] = relationship(lazy='joined')
    node: Mapped['Node | None'] = relationship(lazy='joined')
    department: Mapped['Department'] = relationship(lazy='joined')
    incident_type: Mapped[InternalIncidentType] = relationship(lazy='joined')
    provider: Mapped[Provider | None] = relationship(lazy='joined')
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp())
    @property
    def duration_seconds(self):
        return None if self.end_at is None else (self.end_at - self.start_at).total_seconds()
    acks: Mapped[list['InternalTicketEscalationAck']] = relationship(back_populates='ticket', lazy='raise', passive_deletes='all')

class InternalEscalation(Base):
    __tablename__ = 'internal_escalations'
    __table_args__ = (UniqueConstraint('id', 'ticket_id', name='uq_internal_escalations_id_ticket_id'), CheckConstraint("status IN ('ACTIVE', 'FINISHED')", name='status_values'), CheckConstraint("(status = 'ACTIVE' AND finished_at IS NULL) OR (status = 'FINISHED' AND finished_at IS NOT NULL AND finished_at >= started_at)", name='finish_consistency'), CheckConstraint('department_id IS NOT NULL OR legacy_destination', name='destination_required'), CheckConstraint('length(btrim(description)) > 0 AND length(description) <= 10000', name='description_content'), Index('ix_internal_escalations_chronology', 'ticket_id', 'started_at', 'id'))
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('internal_tickets.id'))
    requester_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    recipient_level: Mapped[str | None] = mapped_column(String(100))
    recipient_position_name: Mapped[str | None] = mapped_column(String(100))
    recipient_department_name: Mapped[str | None] = mapped_column(Text)
    reason_id: Mapped[int] = mapped_column(ForeignKey('escalation_reasons.id'))
    description: Mapped[str] = mapped_column(Text)
    legacy_destination: Mapped[bool] = mapped_column(server_default=text('false'))
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departments.id'))
    position_id: Mapped[int | None] = mapped_column(ForeignKey('positions.id', ondelete='SET NULL'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    status: Mapped[str] = mapped_column(String(8), server_default=text("'ACTIVE'"))
    requester: Mapped[Responsible | None] = relationship(foreign_keys=[requester_id], lazy='joined')
    recipient: Mapped[Responsible | None] = relationship(foreign_keys=[recipient_id], lazy='joined')
    position: Mapped[Position | None] = relationship(foreign_keys=[position_id], lazy='joined')
    reason: Mapped[EscalationReason] = relationship(lazy='joined')

class InternalEscalationAudit(Base):
    __tablename__ = 'internal_escalation_audit'
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    escalation_id: Mapped[int] = mapped_column(ForeignKey('internal_escalations.id'), index=True)
    event: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    changes: Mapped[dict] = mapped_column(JSON)

class InternalTicketUpdate(Base):
    __tablename__ = 'internal_ticket_updates'
    __table_args__ = (ForeignKeyConstraint(['escalation_id', 'ticket_id'], ['internal_escalations.id', 'internal_escalations.ticket_id'], name='fk_internal_updates_escalation_ticket'), CheckConstraint("visibility = 'INTERNAL'", name='internal_only'), CheckConstraint('length(btrim(content)) > 0', name='nonempty_content'), Index('ix_internal_updates_chronology', 'ticket_id', 'occurred_at', 'id'))
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('internal_tickets.id'))
    escalation_id: Mapped[int | None] = mapped_column(index=True)
    content: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    responsible: Mapped[Responsible | None] = relationship(lazy='joined')
    visibility: Mapped[str] = mapped_column(String(8), server_default=text("'INTERNAL'"))
