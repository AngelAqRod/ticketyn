from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields

if TYPE_CHECKING:
    from ticketyn.models.circuit import Circuit


class Customer(CommonFields, Base):
    __tablename__ = "customers"

    customer_code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, index=True)

    circuits: Mapped[list["Circuit"]] = relationship(back_populates="customer")
