"""Documentary installation antecedents; independent of circuit activation."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ticketyn.db.base import Base


SHAPE = """order_type IS NULL OR (order_type = 'NORMAL' AND circuit_id IS NOT NULL AND description IS NULL
    AND service_type_id IS NULL AND node_id IS NULL AND sector_id IS NULL)
    OR (order_type = 'EXTRAORDINARY' AND circuit_id IS NULL AND description IS NOT NULL
    AND service_type_id IS NOT NULL AND node_id IS NOT NULL AND sector_id IS NOT NULL)"""


class InstallationOrder(Base):
    """order_type NULL = legacy order created before modalities existed; it is never classified automatically."""
    __tablename__ = 'installation_orders'
    __table_args__ = (CheckConstraint(SHAPE, name='order_type_shape'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    external_reference: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    order_type: Mapped[str | None] = mapped_column(String(20))
    service: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    service_type_id: Mapped[int | None] = mapped_column(ForeignKey('service_types.id'), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey('nodes.id'), index=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey('sectors.id'), index=True)
    contact: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    circuit_id: Mapped[int | None] = mapped_column(ForeignKey('circuits.id'), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InstallationRequest(Base):
    __tablename__ = 'installation_requests'
    __table_args__ = (
        UniqueConstraint('mailbox', 'folder', 'uidvalidity', 'uid'),
        CheckConstraint("state IN ('PENDING','REVIEWING','PROCESSED','DISCARDED')", name='state_valid'),
        CheckConstraint("(state = 'PROCESSED') = (order_id IS NOT NULL)", name='processed_order'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox: Mapped[str] = mapped_column(String(255))
    folder: Mapped[str] = mapped_column(String(255))
    uidvalidity: Mapped[int] = mapped_column(BigInteger)
    uid: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    sender: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), server_default=text("'PENDING'"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    order_id: Mapped[int | None] = mapped_column(ForeignKey('installation_orders.id'), unique=True)
    discard_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InstallationRequestDraft(Base):
    __tablename__ = 'installation_request_drafts'
    __table_args__ = (CheckConstraint('version > 0', name='version_positive'),)
    request_id: Mapped[int] = mapped_column(ForeignKey('installation_requests.id'), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey('responsibles.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InstallationDocument(Base):
    __tablename__ = 'installation_documents'
    __table_args__ = (
        CheckConstraint('(order_id IS NULL) <> (request_id IS NULL)', name='one_origin'),
        CheckConstraint('size >= 0', name='size_nonnegative'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('installation_orders.id'), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey('installation_requests.id'), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(150))
    size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InstallationEvent(Base):
    __tablename__ = 'installation_events'
    __table_args__ = (CheckConstraint('order_id IS NOT NULL OR request_id IS NOT NULL', name='has_origin'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('installation_orders.id'), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey('installation_requests.id'), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InstallationReceptionFilter(Base):
    """Single row (id=1): who may send installation requests and what the subject must contain."""
    __tablename__ = 'installation_reception_filters'
    id: Mapped[int] = mapped_column(primary_key=True)
    senders: Mapped[list] = mapped_column(JSON, default=list)
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
