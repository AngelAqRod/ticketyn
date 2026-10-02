from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ticketyn.db.base import Base


class TicketNumberConfig(Base):
    __tablename__ = "ticket_number_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("next_number > 0", name="positive_next_number"),
        CheckConstraint("padding >= 0", name="nonnegative_padding"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    prefix: Mapped[str] = mapped_column(String, server_default=text("''"))
    separator: Mapped[str] = mapped_column(String, server_default=text("''"))
    next_number: Mapped[int] = mapped_column(server_default=text("1"))
    padding: Mapped[int] = mapped_column(server_default=text("0"))
