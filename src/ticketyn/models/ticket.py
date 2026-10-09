from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.models.circuit import Circuit
from ticketyn.models.responsible import Responsible

from ticketyn.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("ticket_number > 0", name="positive_ticket_number"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="status_values"),
        CheckConstraint("end_at IS NULL OR end_at >= start_at", name="valid_dates"),
        *(CheckConstraint(f"{field} IS NULL OR (length(btrim({field})) > 0 AND length({field}) <= 10000)", name=f"{field}_content")
          for field in ("resolution", "customer_description", "customer_resolution")),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(unique=True)
    reference: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    customer_description: Mapped[str | None] = mapped_column(Text)
    customer_resolution: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    circuit_id: Mapped[int] = mapped_column(ForeignKey("circuits.id"), index=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    incident_type_id: Mapped[int] = mapped_column(ForeignKey("incident_types.id"), index=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("responsibles.id"), index=True)
    responsible: Mapped[Responsible | None] = relationship(lazy="joined")
    circuit: Mapped[Circuit] = relationship(lazy="joined")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )

    updates: Mapped[list["TicketUpdate"]] = relationship(back_populates="ticket", lazy="raise", passive_deletes="all")

    @property
    def node(self):
        return self.circuit.node

    @property
    def duration_seconds(self) -> float | None:
        if self.end_at is None:
            return None
        return (self.end_at - self.start_at).total_seconds()

    escalations: Mapped[list["TicketEscalation"]] = relationship(back_populates="ticket", lazy="raise")
