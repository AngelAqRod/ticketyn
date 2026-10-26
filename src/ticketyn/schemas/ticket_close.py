from pydantic import AwareDatetime

from ticketyn.schemas.ticket import OptionalTicketText, TicketInput


class TicketClose(TicketInput):
    expected_updated_at: AwareDatetime
    # Omitted/null means the server's time at confirmation, never modal-open time.
    end_at: AwareDatetime | None = None
    resolution: OptionalTicketText | None = None


class CustomerTicketClose(TicketClose):
    customer_resolution: OptionalTicketText | None = None
