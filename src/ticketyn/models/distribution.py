"""Current distribution topology; independent of historical FMS snapshots."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


def normalized_name(column):
    # Keep punctuation and interface numbering: only case and whitespace differ.
    return func.lower(func.btrim(func.regexp_replace(column, '[[:space:]]+', ' ', 'g')).collate('C.utf8'))


class DistributionDevice(CommonFields, Base):
    __tablename__ = 'distribution_devices'
    __table_args__ = (
        UniqueConstraint('id', 'node_id', name='uq_distribution_devices_id_node'),
        CheckConstraint("length(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g'))) > 0", name='name_valid'),
    )
    node_id: Mapped[int] = mapped_column(ForeignKey('nodes.id', ondelete='RESTRICT'))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


Index('uq_distribution_devices_name_normalized', DistributionDevice.node_id, normalized_name(DistributionDevice.name), unique=True)


class PortNomenclature(CommonFields, Base):
    __tablename__ = 'port_nomenclatures'
    __table_args__ = (
        CheckConstraint("length(btrim(prefix)) > 0", name='prefix_valid'),
        CheckConstraint("formats <@ ARRAY['N','X/Y','X/Y/Z','W/X/Y/Z']::text[] AND (NOT active OR cardinality(formats) > 0)", name='formats_valid'),
    )
    name: Mapped[str] = mapped_column(String(255))
    prefix: Mapped[str] = mapped_column(String(200))
    formats: Mapped[list[str]] = mapped_column(ARRAY(Text))


Index('uq_port_nomenclatures_prefix_ci', func.lower(PortNomenclature.prefix.collate('C.utf8')), unique=True)


class DistributionPort(CommonFields, Base):
    __tablename__ = 'distribution_ports'
    __table_args__ = (
        UniqueConstraint('id', 'distribution_device_id', name='uq_distribution_ports_id_device'),
        CheckConstraint("length(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g'))) > 0", name='name_valid'),
        CheckConstraint("""CASE WHEN nomenclature_id IS NULL THEN
            numbering_format IS NULL AND (number_components IS NULL OR number_components = 'null'::jsonb)
            ELSE numbering_format IS NOT NULL AND numbering_format IN ('N','X/Y','X/Y/Z','W/X/Y/Z')
            AND CASE WHEN jsonb_typeof(number_components) = 'array' THEN
                jsonb_array_length(number_components) = CASE numbering_format
                    WHEN 'N' THEN 1 WHEN 'X/Y' THEN 2 WHEN 'X/Y/Z' THEN 3 WHEN 'W/X/Y/Z' THEN 4 END
                ELSE false END END""", name='classification_complete'),
    )
    distribution_device_id: Mapped[int] = mapped_column(ForeignKey('distribution_devices.id', ondelete='RESTRICT'))
    nomenclature_id: Mapped[int | None] = mapped_column(ForeignKey('port_nomenclatures.id', ondelete='RESTRICT'), index=True)
    numbering_format: Mapped[str | None] = mapped_column(String(7))
    number_components: Mapped[list[int] | None] = mapped_column(JSONB)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


Index('uq_distribution_ports_name_normalized', DistributionPort.distribution_device_id, normalized_name(DistributionPort.name), unique=True)


class DistributionAudit(Base):
    __tablename__ = 'distribution_audit'
    __table_args__ = (
        CheckConstraint("resource_type IN ('DEVICE','PORT','CIRCUIT','NOMENCL')", name='resource_valid'),
        CheckConstraint("action IN ('CREATE','EDIT','MOVE','SET_ACTIVE','DELETE','ASSIGN')", name='action_valid'),
        CheckConstraint('resource_id > 0', name='resource_id_valid'),
        Index('ix_distribution_audit_resource', 'resource_type', 'resource_id', 'occurred_at'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id', ondelete='RESTRICT'), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), index=True)
    # No resource FK: an authorized deletion must preserve its audit evidence.
    resource_type: Mapped[str] = mapped_column(String(10))
    resource_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(12))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
