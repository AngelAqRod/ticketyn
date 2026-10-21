"""Persistent security foundation. Session tokens never enter PostgreSQL."""
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, Integer, Boolean, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ticketyn.db.base import Base

DEFAULT_ROLES = (
    ('SUPERADMIN', 'Superadministrador'), ('ADMIN', 'Administrador'),
    ('OPERATOR', 'Operador'), ('AUDITOR', 'Auditor / Solo lectura'),
)

class SecurityRole(Base):
    __tablename__ = 'security_roles'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(server_default='0')

Index('uq_security_roles_name_ci', func.lower(SecurityRole.name.collate('C.utf8')), unique=True)

class SecurityPermission(Base):
    __tablename__ = 'security_permissions'
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    description: Mapped[str] = mapped_column(String(300))

class SecurityRolePermission(Base):
    __tablename__ = 'security_role_permissions'
    role_id: Mapped[int] = mapped_column(ForeignKey('security_roles.id', ondelete='CASCADE'), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey('security_permissions.code', ondelete='CASCADE'), primary_key=True)

class SecurityConfig(Base):
    __tablename__ = 'security_config'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'), CheckConstraint('idle_minutes >= 3 AND idle_minutes <= 1440', name='idle_range'))
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    idle_minutes: Mapped[int] = mapped_column(server_default='30')
    audit_retention_days: Mapped[int] = mapped_column(server_default='365')
    failure_retention_days: Mapped[int] = mapped_column(server_default='7')

class SecurityAudit(Base):
    __tablename__ = 'security_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id', ondelete='RESTRICT'), index=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey('responsibles.id', ondelete='RESTRICT'))
    event: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(100), default='HTTP')
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only explicitly whitelisted non-secret metadata belongs here.
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
