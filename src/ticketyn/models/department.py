from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Department(CommonFields, Base):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String, unique=True)
