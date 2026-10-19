"""Current technical request state only; never a message or resend history."""
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from ticketyn.db.base import Base


class MailProcessorControl(Base):
    __tablename__ = 'mail_processor_control'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    paused: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    reason: Mapped[str] = mapped_column(String(40), server_default=text("'INITIAL_SETUP'"))
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    database_oid: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), onupdate=func.clock_timestamp())


class MailNotificationRequest(Base):
    __tablename__ = 'mail_notification_requests'
    __table_args__ = (
        UniqueConstraint('event_key', 'activation_id'),
        CheckConstraint("event_key = 'fms.activation.created'", name='event_supported'),
        CheckConstraint("state IN ('PENDING','PREPARING','SENDING','ACCEPTED','FAILED','PARTIAL','UNCERTAIN','CANCELLED')", name='state_valid'),
        CheckConstraint("source IN ('AUTOMATIC','MANUAL')", name='source_valid'),
        CheckConstraint('revision > 0', name='revision_positive'),
        Index('ix_mail_requests_state', 'state'),
        Index('ix_mail_requests_pending', 'requested_at', 'id', postgresql_where=text("state = 'PENDING'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), ForeignKey('mail_event_config.event_key', ondelete='RESTRICT'))
    activation_id: Mapped[int] = mapped_column(ForeignKey('activations.id', ondelete='RESTRICT'), index=True)
    state: Mapped[str] = mapped_column(String(20), server_default=text("'PENDING'"))
    source: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    owner_token: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    preparing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
