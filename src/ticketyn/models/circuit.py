from typing import TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields

if TYPE_CHECKING:
    from ticketyn.models.customer import Customer
    from ticketyn.models.node import Node


class Circuit(CommonFields, Base):
    __tablename__ = "circuits"

    cpe_model_id: Mapped[int | None] = mapped_column(ForeignKey('cpe_models.id'), index=True)
    cpe_model: Mapped['CpeModel | None'] = relationship(lazy='joined')
    cpe_management_ip: Mapped[str | None] = mapped_column(INET)
    cpe_configuration: Mapped[str | None] = mapped_column(Text, deferred=True)

    __table_args__ = (
        CheckConstraint("masklen(cpe_management_ip) = CASE family(cpe_management_ip) WHEN 4 THEN 32 ELSE 128 END", name="cpe_management_ip_host"),
        CheckConstraint("(initial_capacity IS NULL AND initial_capacity_unit IS NULL) OR (initial_capacity IS NOT NULL AND initial_capacity > 0 AND initial_capacity <> 'NaN'::numeric AND initial_capacity_unit IS NOT NULL AND initial_capacity_unit IN ('Mbps','Gbps'))", name='initial_capacity_valid'),
        CheckConstraint('distribution_device_id IS NULL OR node_id IS NOT NULL', name='distribution_node_required'),
        CheckConstraint('distribution_port_id IS NULL OR distribution_device_id IS NOT NULL', name='distribution_device_required'),
        ForeignKeyConstraint(['distribution_device_id', 'node_id'], ['distribution_devices.id', 'distribution_devices.node_id'], name='fk_circuits_distribution_device_node', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['distribution_port_id', 'distribution_device_id'], ['distribution_ports.id', 'distribution_ports.distribution_device_id'], name='fk_circuits_distribution_port_device', ondelete='RESTRICT', onupdate='RESTRICT'),
        Index('ix_circuits_distribution_device_node', 'distribution_device_id', 'node_id'),
        Index('ix_circuits_distribution_port_device', 'distribution_port_id', 'distribution_device_id'),
    )
    distribution_device_id: Mapped[int | None] = mapped_column()
    distribution_port_id: Mapped[int | None] = mapped_column()
    # Read-only projections: FK values are assigned explicitly after validation.
    distribution_device: Mapped['DistributionDevice | None'] = relationship(
        'DistributionDevice', primaryjoin='Circuit.distribution_device_id == DistributionDevice.id',
        foreign_keys=[distribution_device_id], viewonly=True, lazy='joined')
    distribution_port: Mapped['DistributionPort | None'] = relationship(
        'DistributionPort', primaryjoin='Circuit.distribution_port_id == DistributionPort.id',
        foreign_keys=[distribution_port_id], viewonly=True, lazy='joined')
    initial_capacity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    initial_capacity_unit: Mapped[str | None] = mapped_column(String(4))

    service_type_id: Mapped[int | None] = mapped_column(ForeignKey('service_types.id'), index=True)
    service_type: Mapped['ServiceType | None'] = relationship(lazy='joined')

    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), index=True)
    sector: Mapped["Sector | None"] = relationship(lazy="joined")

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), index=True)
    node: Mapped["Node | None"] = relationship(lazy="joined")
    circuit_code: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(Text, index=True)

    customer: Mapped["Customer"] = relationship(back_populates="circuits")
