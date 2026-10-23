"""Individual NOC report, using the existing Tickets document primitives."""
from functools import partial

from sqlalchemy import select, func
from ticketyn.api.crud import get_or_404
from ticketyn.api.documents import build_pdf, fonts, modern_table, paragraph, section, MUTED, PURPLE, BLUE, EMERALD, AMBER, CYAN, MODULAR_WIDTH, ModularHeading, identification, metadata_modules, timeline_entry
from ticketyn.api.ticket_reports import date_text, timing_rows, intervention_block, append_escalations
from ticketyn.api.ticket_update_data import list_updates
from ticketyn.api.escalation_data import list_escalations
from ticketyn.models import InternalTicket, InternalTicketUpdate, InternalEscalation, Ticket, Customer


def internal_ticket_pdf(session, ticket_id, output, zone, issued):
    fonts()
    section = partial(ModularHeading, accent=PURPLE)
    ticket = get_or_404(session, InternalTicket, ticket_id)
    rows = [['Sector', ticket.sector.name], ['Nodo', ticket.node.name if ticket.node else 'Sin asignar'],
            ['Departamento', ticket.department.name],
            ['Responsable', ticket.responsible.name if ticket.responsible else 'Sin asignar'],
            ['Tipo de incidencia interna', ticket.incident_type.name],
            ['Atribuible a proveedor', ticket.provider.name if ticket.provider else 'Ninguno'],
            *timing_rows(ticket, zone, issued)]
    story = [identification(ticket.reference, ticket.title, ticket.status, 'Reporte interno de incidencia', date_text(ticket.start_at, zone), accent=PURPLE),
             section('Clasificación y tiempos operativos'), metadata_modules(rows),
             *intervention_block(section('Descripción original', accent=BLUE), paragraph(ticket.description, size=10), modular=True),
             *intervention_block(section('Resolución documentada', accent=EMERALD), paragraph(ticket.resolution or 'Sin resolución documentada.', size=10), modular=True)]
    history_heading = section('Seguimiento cronológico · Uso interno', accent=CYAN, keep=False)
    updates = list_updates(session, ticket_id, Ticket=InternalTicket, TicketUpdate=InternalTicketUpdate)
    if not updates:
        history_heading.style.keepWithNext = True
        story.extend([history_heading, paragraph('Sin intervenciones registradas.', size=10)])
    for index, update in enumerate(updates):
        story.append(timeline_entry(date_text(update.occurred_at, zone), update.content,
            responsible=update.responsible.name if update.responsible else 'Sin asignar',
            association=f'Escalamiento #{update.escalation_id}' if update.escalation_id is not None else None,
            accent=CYAN, section_heading=history_heading if index == 0 else None))
    append_escalations(story, list_escalations(session, ticket_id, TicketEscalation=InternalEscalation), zone, modular=True, accent=AMBER)
    total = session.scalar(select(func.count(Ticket.id)).where(Ticket.internal_ticket_id == ticket_id))
    related = session.execute(select(Ticket.reference, Customer.name, Ticket.title, Ticket.status)
                             .join(Customer, Ticket.customer_id == Customer.id)
                             .where(Ticket.internal_ticket_id == ticket_id)
                             .order_by(Ticket.created_at, Ticket.id).execution_options(yield_per=200))
    story.extend([section('Tickets de clientes relacionados'), paragraph(f'Total: {total}', size=9, keep=bool(total))])
    if total:
        story.append(modern_table(['Correlativo', 'Cliente', 'Incidencia', 'Estado'],
            ([ref, customer, title, 'Abierto' if status == 'OPEN' else 'Cerrado'] for ref, customer, title, status in related),
            [MODULAR_WIDTH * part for part in (.22, .24, .40, .14)], reference=True, light=True))
    else:
        story.append(paragraph('Sin tickets de clientes relacionados', size=10))
    build_pdf(output, 'Reporte interno de incidencia', str(zone), story, issued_at=date_text(issued, zone), modular=True, reference=ticket.reference, accent=PURPLE)
