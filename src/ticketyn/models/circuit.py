from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields

if TYPE_CHECKING:
    from ticketyn.models.customer import Customer
    from ticketyn.models.node import Node


class Circuit(CommonFields, Base):
    __tablename__ = "circuits"

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), index=True)
    node: Mapped["Node | None"] = relationship(lazy="joined")
    circuit_code: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(Text, index=True)

    customer: Mapped["Customer"] = relationship(back_populates="circuits")
