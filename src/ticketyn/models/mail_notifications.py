"""Administrative mail settings only. No messages, jobs or plaintext secrets."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ticketyn.db.base import Base


class MailTransportConfig(Base):
    __tablename__ = 'mail_transport_config'
    __table_args__ = (
        CheckConstraint('id = 1', name='singleton'),
        CheckConstraint('port BETWEEN 1 AND 65535', name='port_valid'),
        CheckConstraint("security IN ('STARTTLS','IMPLICIT_TLS','NONE')", name='security_valid'),
        CheckConstraint("auth_method IN ('NONE','PASSWORD','OAUTH2_DELEGATED','OAUTH2_APPLICATION')", name='auth_valid'),
        CheckConstraint("security <> 'NONE' OR allow_unencrypted", name='unencrypted_opt_in'),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    host: Mapped[str | None] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(server_default=text('587'))
    security: Mapped[str] = mapped_column(String(20), server_default=text("'STARTTLS'"))
    allow_unencrypted: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    sender_email: Mapped[str | None] = mapped_column(String(254))
    sender_name: Mapped[str] = mapped_column(String(200), server_default=text("''"))
    auth_method: Mapped[str] = mapped_column(String(30), server_default=text("'NONE'"))
    provider: Mapped[str | None] = mapped_column(String(30))
    username: Mapped[str | None] = mapped_column(String(254))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    oauth_settings: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    oauth_status: Mapped[str] = mapped_column(String(32), server_default=text("'UNCONFIGURED'"))
    test_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    test_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    test_lease_token: Mapped[str | None] = mapped_column(String(64))
    # OAuth client secrets, tokens, PKCE verifier and pending state are encrypted.
    oauth_credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), onupdate=func.clock_timestamp())


class MailEventConfig(Base):
    __tablename__ = 'mail_event_config'
    __table_args__ = (
        CheckConstraint("mode IN ('AUTOMATIC','MANUAL','DISABLED')", name='mode_valid'),
        CheckConstraint("jsonb_typeof(to_recipients) = 'array' AND jsonb_typeof(cc_recipients) = 'array' AND jsonb_typeof(bcc_recipients) = 'array'", name='recipients_arrays'),
    )
    template: Mapped[dict | None] = mapped_column(JSONB)
    event_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), server_default=text("'DISABLED'"))
    to_recipients: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    cc_recipients: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    bcc_recipients: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), onupdate=func.clock_timestamp())
