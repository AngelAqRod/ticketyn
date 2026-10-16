"""Individual NOC report, using the existing Tickets document primitives."""
from sqlalchemy import select, func
from ticketyn.api.crud import get_or_404
from ticketyn.api.documents import build_pdf, fonts, modern_table, paragraph, section, MUTED
from ticketyn.api.ticket_reports import date_text, timing_rows, intervention_block, append_escalations
from ticketyn.api.ticket_update_data import list_updates
from ticketyn.api.escalation_data import list_escalations
from ticketyn.models import InternalTicket, InternalTicketUpdate, InternalEscalation, Ticket, Customer


def internal_ticket_pdf(session, ticket_id, output, zone, issued):
    fonts()
    ticket = get_or_404(session, InternalTicket, ticket_id)
    rows = [['Sector', ticket.sector.name], ['Nodo', ticket.node.name if ticket.node else 'Sin asignar'],
            ['Departamento', ticket.department.name],
            ['Responsable', ticket.responsible.name if ticket.responsible else 'Sin asignar'],
            ['Tipo de incidencia interna', ticket.incident_type.name],
            ['Atribuible a proveedor', ticket.provider.name if ticket.provider else 'Ninguno'],
            *timing_rows(ticket, zone, issued)]
    story = [paragraph(ticket.reference, size=18, bold=True, keep=True),
             paragraph(ticket.title, size=12, color=MUTED), section('Clasificación y tiempos operativos'),
             modern_table(['Dato', 'Valor'], rows, [250, 530], compact=True),
             section('Descripción original'), paragraph(ticket.description, size=10),
             section('Resolución documentada'), paragraph(ticket.resolution or 'Sin resolución documentada.', size=10)]
    history_heading = section('Seguimiento cronológico · Uso interno', keep=False)
    updates = list_updates(session, ticket_id, Ticket=InternalTicket, TicketUpdate=InternalTicketUpdate)
    if not updates:
        history_heading.style.keepWithNext = True
        story.extend([history_heading, paragraph('Sin intervenciones registradas.', size=10)])
    for index, update in enumerate(updates):
        association = f' · Escalamiento #{update.escalation_id}' if update.escalation_id is not None else ''
        heading = paragraph(f'{date_text(update.occurred_at, zone)} · {update.responsible.name if update.responsible else "Sin asignar"}{association}', bold=True, size=9)
        story.extend(intervention_block(heading, paragraph(update.content, size=10), history_heading if index == 0 else None))
    append_escalations(story, list_escalations(session, ticket_id, TicketEscalation=InternalEscalation), zone)
    total = session.scalar(select(func.count(Ticket.id)).where(Ticket.internal_ticket_id == ticket_id))
    related = session.execute(select(Ticket.reference, Customer.name, Ticket.title, Ticket.status)
                             .join(Customer, Ticket.customer_id == Customer.id)
                             .where(Ticket.internal_ticket_id == ticket_id)
                             .order_by(Ticket.created_at, Ticket.id).execution_options(yield_per=200))
    story.extend([section('Tickets de clientes relacionados'), paragraph(f'Total: {total}', size=9)])
    if total:
        story.append(modern_table(['Correlativo', 'Cliente', 'Incidencia', 'Estado'],
            ([ref, customer, title, 'Abierto' if status == 'OPEN' else 'Cerrado'] for ref, customer, title, status in related),
            [140, 180, 360, 100], reference=True))
    else:
        story.append(paragraph('Sin tickets de clientes relacionados', size=10))
    build_pdf(output, 'Reporte interno de incidencia', str(zone), story, issued_at=date_text(issued, zone))
