from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.responsible import Responsible


class TicketUpdate(Base):
    """Intervención registrada; independiente del ciclo de vida del ticket."""

    __tablename__ = "ticket_updates"
    __table_args__ = (
        CheckConstraint("visibility IN ('INTERNAL', 'PUBLIC')", name="visibility_values"),
        CheckConstraint("length(btrim(content)) > 0", name="nonempty_content"),
        Index("ix_ticket_updates_ticket_chronology", "ticket_id", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    content: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("responsibles.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(8), server_default="INTERNAL")
    ticket: Mapped["Ticket"] = relationship(back_populates="updates", lazy="raise")
    responsible: Mapped[Responsible | None] = relationship(lazy="joined")
