"""Planned NOC changes; independent numbering and operational history."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields

class ChangeType(CommonFields, Base):
    __tablename__ = 'change_types'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

Index('uq_change_types_name_normalized', func.lower(func.btrim(ChangeType.name).collate('C.utf8')), unique=True)

class ChangeCompletionType(CommonFields, Base):
    __tablename__ = 'change_completion_types'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    applies_efficiency: Mapped[bool] = mapped_column(default=False, server_default=text('false'))

Index('uq_change_completion_types_name_normalized', func.lower(func.btrim(ChangeCompletionType.name).collate('C.utf8')), unique=True)

class ChangeNumberConfig(Base):
    __tablename__ = 'change_number_config'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'), CheckConstraint('next_number > 0', name='positive_next_number'), CheckConstraint('padding >= 0', name='nonnegative_padding'))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    prefix: Mapped[str] = mapped_column(String, server_default=text("'CAM'"))
    separator: Mapped[str] = mapped_column(String, server_default=text("'-'"))
    next_number: Mapped[int] = mapped_column(server_default=text('1'))
    padding: Mapped[int] = mapped_column(server_default=text('7'))

class MaintenanceChange(Base):
    __tablename__ = 'maintenance_changes'
    __table_args__ = (
        CheckConstraint("status IN ('SCHEDULED','EXECUTING','FINISHED')", name='status_values'),
        CheckConstraint('proposed_end >= proposed_start', name='proposed_dates'),
        CheckConstraint('actual_end IS NULL OR (actual_start IS NOT NULL AND actual_end >= actual_start)', name='actual_dates'),
        CheckConstraint("status = 'SCHEDULED' OR actual_start IS NOT NULL", name='execution_start'),
        CheckConstraint("status <> 'FINISHED' OR (actual_end IS NOT NULL AND completion_type_id IS NOT NULL AND efficiency_eligible IS NOT NULL AND completion_name IS NOT NULL AND final_notes IS NOT NULL AND length(btrim(final_notes)) > 0)", name='finish_required'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(unique=True)
    reference: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    sector_id: Mapped[int] = mapped_column(ForeignKey('sectors.id'), index=True)
    change_type_id: Mapped[int | None] = mapped_column(ForeignKey('change_types.id'), index=True)
    change_type: Mapped['ChangeType | None'] = relationship(lazy='joined')
    node_id: Mapped[int | None] = mapped_column(ForeignKey('nodes.id'), index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), index=True)
    manager_name: Mapped[str] = mapped_column(Text)
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), index=True)
    department_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), index=True)
    proposed_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    proposed_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_type_id: Mapped[int | None] = mapped_column(ForeignKey('change_completion_types.id'), index=True)
    completion_name: Mapped[str | None] = mapped_column(Text)
    efficiency_eligible: Mapped[bool | None] = mapped_column(Boolean)
    final_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), onupdate=func.clock_timestamp())
    sector: Mapped['Sector'] = relationship(lazy='joined')
    node: Mapped['Node | None'] = relationship(lazy='joined')
    support: Mapped[list['ChangeSupport']] = relationship(lazy='selectin', order_by='ChangeSupport.person_id')
    tickets: Mapped[list['ChangeTicket']] = relationship(lazy='selectin', order_by='ChangeTicket.internal_ticket_id')

class ChangeSupport(Base):
    __tablename__ = 'change_support'
    change_id: Mapped[int] = mapped_column(ForeignKey('maintenance_changes.id'), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), primary_key=True, index=True)
    person_name: Mapped[str] = mapped_column(Text)

class ChangeTicket(Base):
    __tablename__ = 'change_tickets'
    change_id: Mapped[int] = mapped_column(ForeignKey('maintenance_changes.id'), primary_key=True)
    internal_ticket_id: Mapped[int] = mapped_column(ForeignKey('internal_tickets.id'), primary_key=True, index=True)
    ticket: Mapped['InternalTicket'] = relationship(lazy='joined')

class ChangeUpdate(Base):
    __tablename__ = 'change_updates'
    __table_args__ = (Index('ix_change_updates_chronology', 'change_id', 'occurred_at', 'id'),)
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey('maintenance_changes.id'))
    responsible_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    responsible_name: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ChangeAudit(Base):
    __tablename__ = 'change_audit'
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey('maintenance_changes.id'), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    changes: Mapped[dict] = mapped_column(JSON)
