"""Client activation certificate: a positive projection, never an ORM renderer."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from ticketyn.api.documents import EMERALD, ModularHeading, build_pdf, fonts, identification, metadata_modules, paragraph
from ticketyn.api.fms_exports import capacity_text
from ticketyn.api.ticket_reports import date_text, intervention_block
from ticketyn.models.fms import Activation


@dataclass(frozen=True)
class CustomerActivationReport:
    reference: str
    customer_name: str | None
    circuit_code: str | None
    service_type_name: str | None
    effective_at: datetime
    initial_capacity: Decimal | None
    initial_capacity_unit: str | None
    customer_activation_notes: str | None


def customer_activation_report(session, activation_id):
    row = session.execute(select(
        Activation.reference, Activation.customer_name_snapshot.label('customer_name'),
        Activation.circuit_code_snapshot.label('circuit_code'),
        Activation.service_type_name, Activation.effective_at, Activation.initial_capacity,
        Activation.initial_capacity_unit, Activation.customer_activation_notes,
    ).where(Activation.id == activation_id)).one_or_none()
    if row is None:
        raise HTTPException(404, 'Activación no encontrada')
    return CustomerActivationReport(**row._mapping)


def customer_activation_pdf(report: CustomerActivationReport, output, zone, issued):
    fonts()
    title = 'Constancia de activación de servicio'
    fields = [('Cliente', report.customer_name or 'No registrado'), ('Código del circuito', report.circuit_code or 'No registrado'),
              ('Tipo de servicio', report.service_type_name or 'No registrado'),
              ('Fecha efectiva de activación', date_text(report.effective_at, zone))]
    if report.initial_capacity is not None:
        fields.append(('Capacidad inicial', capacity_text(report.initial_capacity, report.initial_capacity_unit)))
    story = [identification(report.reference, title, 'ACTIVA', 'Documento para cliente',
        f'Emitido: {date_text(issued, zone)}', accent=EMERALD,
        capsule_label='Activación registrada', capsule_color=EMERALD),
        ModularHeading('Información del servicio', accent=EMERALD), metadata_modules(fields)]
    story.extend(intervention_block(ModularHeading('Información de entrega del servicio', accent=EMERALD),
        paragraph(report.customer_activation_notes or 'Sin información de entrega registrada.', size=10), modular=True))
    build_pdf(output, title, str(zone), story, issued_at=date_text(issued, zone),
        modular=True, reference=report.reference, accent=EMERALD)
