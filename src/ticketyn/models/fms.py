"""Registros operativos de circuitos; independientes de tickets."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class DeactivationReason(CommonFields, Base):
    __tablename__ = 'deactivation_reasons'
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


Index('uq_deactivation_reasons_name_normalized', func.lower(func.btrim(DeactivationReason.name).collate('C.utf8')), unique=True)


class ActivationNumberConfig(Base):
    __tablename__ = 'activation_number_config'
    __table_args__ = (CheckConstraint('id = 1', name='singleton'), CheckConstraint('next_number > 0', name='positive_next_number'), CheckConstraint('padding >= 0 AND padding <= 20', name='padding_range'))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    prefix: Mapped[str] = mapped_column(String, server_default=text("'ACT'"))
    separator: Mapped[str] = mapped_column(String, server_default=text("'-'"))
    next_number: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    padding: Mapped[int] = mapped_column(server_default=text('6'))


class OperationFields:
    node_id: Mapped[int | None] = mapped_column(ForeignKey('nodes.id'), index=True)

    @declared_attr
    def node(cls):
        return relationship('Node', lazy='joined')

    sector_id: Mapped[int | None] = mapped_column(ForeignKey('sectors.id'), index=True)

    @declared_attr
    def sector(cls):
        return relationship('Sector', lazy='joined')

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    circuit_id: Mapped[int] = mapped_column(ForeignKey('circuits.id'), index=True)
    responsible_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class Activation(OperationFields, Base):
    __tablename__ = 'activations'
    distribution_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    distribution_device_name: Mapped[str | None] = mapped_column(String(255))
    distribution_port_name: Mapped[str | None] = mapped_column(String(255))
    activation_notes: Mapped[str | None] = mapped_column(Text)
    customer_activation_notes: Mapped[str | None] = mapped_column(Text)
    customer_name_snapshot: Mapped[str | None] = mapped_column(Text)
    circuit_code_snapshot: Mapped[str | None] = mapped_column(Text)
    cpe_activation: Mapped[str | None] = mapped_column(Text)
    service_type_name: Mapped[str | None] = mapped_column(String)
    initial_capacity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    initial_capacity_unit: Mapped[str | None] = mapped_column(String(4))
    activation_number: Mapped[int] = mapped_column(unique=True)
    reference: Mapped[str] = mapped_column(String, unique=True)
    circuit: Mapped['Circuit'] = relationship(lazy='joined')
    responsible: Mapped['Responsible'] = relationship(lazy='joined')
    __table_args__ = (
        CheckConstraint('distribution_recorded OR (distribution_device_name IS NULL AND distribution_port_name IS NULL)', name='distribution_recorded_valid'),
        CheckConstraint('distribution_port_name IS NULL OR distribution_device_name IS NOT NULL', name='distribution_device_required'),
        CheckConstraint("(initial_capacity IS NULL AND initial_capacity_unit IS NULL) OR (initial_capacity IS NOT NULL AND initial_capacity > 0 AND initial_capacity <> 'NaN'::numeric AND initial_capacity_unit IS NOT NULL AND initial_capacity_unit IN ('Mbps','Gbps'))", name='initial_capacity_valid'), CheckConstraint('activation_number > 0', name='positive_number'), Index('ix_activations_chronology', 'circuit_id', 'effective_at', 'id'))


class ActivationIntervention(Base):
    __tablename__ = 'activation_interventions'
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    activation_id: Mapped[int] = mapped_column(ForeignKey('activations.id'), index=True)
    responsible_id: Mapped[int] = mapped_column(ForeignKey('responsibles.id'), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    content: Mapped[str] = mapped_column(Text)
    responsible: Mapped['Responsible'] = relationship(lazy='joined')
    __table_args__ = (CheckConstraint('length(btrim(content)) > 0 AND length(content) <= 10000', name='content_valid'), Index('ix_activation_interventions_chronology', 'activation_id', 'occurred_at', 'id'))


class CapacityChange(OperationFields, Base):
    __tablename__ = 'capacity_changes'
    operation_type: Mapped[str] = mapped_column(String(10))
    previous_capacity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    previous_unit: Mapped[str | None] = mapped_column(String(4))
    new_capacity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    new_unit: Mapped[str] = mapped_column(String(4))
    description: Mapped[str | None] = mapped_column(Text)
    circuit: Mapped['Circuit'] = relationship(lazy='joined')
    responsible: Mapped['Responsible'] = relationship(lazy='joined')
    __table_args__ = (
        CheckConstraint("operation_type IN ('INCREASE','DECREASE')", name='type_valid'),
        CheckConstraint("new_capacity > 0 AND new_capacity <> 'NaN'::numeric AND new_unit IN ('Mbps','Gbps')", name='new_valid'),
        CheckConstraint("(previous_capacity IS NULL AND previous_unit IS NULL AND operation_type = 'INCREASE') OR (previous_capacity IS NOT NULL AND previous_capacity > 0 AND previous_capacity <> 'NaN'::numeric AND previous_unit IS NOT NULL AND previous_unit IN ('Mbps','Gbps'))", name='previous_valid'),
        CheckConstraint("previous_capacity IS NULL OR (operation_type = 'INCREASE' AND new_capacity * CASE new_unit WHEN 'Gbps' THEN 1000 ELSE 1 END > previous_capacity * CASE previous_unit WHEN 'Gbps' THEN 1000 ELSE 1 END) OR (operation_type = 'DECREASE' AND new_capacity * CASE new_unit WHEN 'Gbps' THEN 1000 ELSE 1 END < previous_capacity * CASE previous_unit WHEN 'Gbps' THEN 1000 ELSE 1 END)", name='direction_valid'),
        Index('ix_capacity_changes_chronology', 'circuit_id', 'effective_at', 'id'),
    )


class CircuitLifecycleOperation(OperationFields, Base):
    __tablename__ = 'circuit_lifecycle_operations'
    operation_type: Mapped[str] = mapped_column(String(12))
    reason_id: Mapped[int | None] = mapped_column(ForeignKey('deactivation_reasons.id'), index=True)
    observations: Mapped[str | None] = mapped_column(Text)
    circuit: Mapped['Circuit'] = relationship(lazy='joined')
    responsible: Mapped['Responsible'] = relationship(lazy='joined')
    reason: Mapped[DeactivationReason | None] = relationship(lazy='joined')
    __table_args__ = (CheckConstraint("(operation_type = 'DEACTIVATE' AND reason_id IS NOT NULL) OR (operation_type = 'REACTIVATE' AND reason_id IS NULL)", name='reason_valid'), Index('ix_circuit_lifecycle_chronology', 'circuit_id', 'effective_at', 'id'))
