from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Node(CommonFields, Base):
    __tablename__ = "nodes"

    name: Mapped[str] = mapped_column(String, unique=True)
