"""Resource limits for bulk ticket PDFs in the supported single HTTP worker."""
from contextlib import contextmanager
import math
import threading
import time

from fastapi import HTTPException
from sqlalchemy import func

MAX_TICKETS = 2000
MAX_TEXT_CHARACTERS = 2_000_000
PDF_INTERVAL = 30


class TicketPdfLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.busy = False
        self.next_allowed = {}

    @contextmanager
    def reserve(self, user_id):
        with self.lock:
            now = self.clock()
            self.next_allowed = {id: until for id, until in self.next_allowed.items() if until > now}
            waiting = self.next_allowed.get(user_id, now) - now
            if waiting > 0 or self.busy:
                raise HTTPException(429, 'Espera antes de solicitar otro PDF de tickets.',
                                    headers={'Retry-After': str(math.ceil(waiting) if waiting > 0 else 5)})
            self.busy = True
            self.next_allowed[user_id] = now + PDF_INTERVAL
        try:
            yield
        finally:
            with self.lock:
                self.busy = False


@contextmanager
def ticket_pdf_export(request, format):
    if format == 'pdf':
        with request.app.state.ticket_pdf_limiter.reserve(request.state.principal.id):
            yield
    else:
        yield


def validate_pdf_volume(session, filters, *, internal=False):
    """Measure text in PostgreSQL before loading records or building ReportLab cells."""
    from ticketyn.api import ticket_data, internal_ticket_data
    from ticketyn.models import Ticket, InternalTicket, Circuit, Customer, Node, Responsible

    values = filters.ticket_filters() if hasattr(filters, 'ticket_filters') else filters.model_dump()
    model = InternalTicket if internal else Ticket
    relations = internal_ticket_data.RELATIONS if internal else {
        **ticket_data.RELATED_MODELS, 'node_id': Node, 'responsible_id': Responsible}
    query = internal_ticket_data.statement(values) if internal else ticket_data.ticket_statement(values)
    columns = [model.reference, model.title, model.description, model.resolution]
    for field, catalog in relations.items():
        query = query.outerjoin(catalog, getattr(model, field) == catalog.id)
        if catalog is not Circuit:
            columns.append(catalog.name)
    if not internal:
        columns.extend([Customer.customer_code, Circuit.circuit_code, Circuit.description])
    # Include narrative fields conservatively, plus space for dates and generated labels.
    text_size = 256 + sum(func.coalesce(func.char_length(column), 0) for column in columns)
    count, characters = session.execute(query.order_by(None).with_only_columns(
        func.count(), func.coalesce(func.sum(text_size), 0))).one()
    if count > MAX_TICKETS:
        raise HTTPException(413, f'El PDF supera {MAX_TICKETS} tickets. Reduce el período o aplica filtros.')
    characters += sum(len(str(value)) for value in values.values() if value is not None)
    if characters > MAX_TEXT_CHARACTERS:
        raise HTTPException(413, 'El contenido del PDF es demasiado extenso. Reduce el período o aplica filtros.')
