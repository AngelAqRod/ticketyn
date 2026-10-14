from typing import TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields

if TYPE_CHECKING:
    from ticketyn.models.customer import Customer
    from ticketyn.models.node import Node


class Circuit(CommonFields, Base):
    __tablename__ = "circuits"

    __table_args__ = (CheckConstraint("(initial_capacity IS NULL AND initial_capacity_unit IS NULL) OR (initial_capacity IS NOT NULL AND initial_capacity > 0 AND initial_capacity <> 'NaN'::numeric AND initial_capacity_unit IS NOT NULL AND initial_capacity_unit IN ('Mbps','Gbps'))", name='initial_capacity_valid'),)
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
