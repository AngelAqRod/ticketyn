"""Administrative requests: an operational log that may point at existing records."""
from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class AdminRequestType(CommonFields, Base):
    __tablename__ = 'admin_request_types'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


Index('uq_admin_request_types_name_normalized', func.lower(func.btrim(AdminRequestType.name).collate('C.utf8')), unique=True)


class AdminRequestNumberConfig(Base):
    __tablename__ = 'admin_request_number_config'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'), CheckConstraint('next_number > 0', name='positive_next_number'), CheckConstraint('padding >= 0', name='nonnegative_padding'))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    prefix: Mapped[str] = mapped_column(String, server_default=text("'SOL'"))
    separator: Mapped[str] = mapped_column(String, server_default=text("'-'"))
    next_number: Mapped[int] = mapped_column(server_default=text('1'))
    padding: Mapped[int] = mapped_column(server_default=text('7'))


class AdminRequest(Base):
    __tablename__ = 'admin_requests'
    __table_args__ = (CheckConstraint("status IN ('REGISTERED','IN_PROGRESS','COMPLETED','CANCELLED')", name='status_valid'),
                      CheckConstraint('application_start IS NULL OR application_end IS NULL OR application_end >= application_start', name='period_valid'))
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(unique=True)
    reference: Mapped[str] = mapped_column(String, unique=True)
    request_date: Mapped[date] = mapped_column(Date, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('customers.id'), index=True)
    circuit_id: Mapped[int | None] = mapped_column(ForeignKey('circuits.id'), index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey('admin_request_types.id'), index=True)
    description: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), server_default='REGISTERED', index=True)
    application_start: Mapped[date | None] = mapped_column(Date)
    application_end: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    links: Mapped[list['AdminRequestLink']] = relationship(lazy='selectin', order_by='AdminRequestLink.id')


class AdminRequestLink(Base):
    """Exactly one target column is set; unique constraints block duplicate associations."""
    __tablename__ = 'admin_request_links'
    __table_args__ = (
        CheckConstraint('num_nonnulls(ticket_id, internal_ticket_id, change_id) = 1', name='one_target'),
        UniqueConstraint('request_id', 'ticket_id', name='uq_admin_request_links_ticket_id'),
        UniqueConstraint('request_id', 'internal_ticket_id', name='uq_admin_request_links_internal_ticket_id'),
        UniqueConstraint('request_id', 'change_id', name='uq_admin_request_links_change_id'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('admin_requests.id'), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'), index=True)
    internal_ticket_id: Mapped[int | None] = mapped_column(ForeignKey('internal_tickets.id'), index=True)
    change_id: Mapped[int | None] = mapped_column(ForeignKey('maintenance_changes.id'), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminRequestEvent(Base):
    __tablename__ = 'admin_request_events'
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('admin_requests.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
