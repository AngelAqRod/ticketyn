"""Modern Modular opt-in composition and reproducible fictitious PDF examples."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import re
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from reportlab.lib.pagesizes import A4

from ticketyn.api import documents, ticket_reports, internal_ticket_reports
from test_ticket_pdf_layout import rendered  # shared text/page capture fixture


def sample_ticket():
    now = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)
    return SimpleNamespace(
        reference='DEMO-000042', title='Intermitencia del enlace de acceso empresarial',
        status='CLOSED', start_at=now - timedelta(hours=2), end_at=now,
        customer=SimpleNamespace(name='Cliente ficticio Horizonte', customer_code='DEMO-CLIENTE'),
        circuit=SimpleNamespace(circuit_code='DEMO-CIR-042'),
        sector=SimpleNamespace(name='Sector de laboratorio'), node=SimpleNamespace(name='Nodo de laboratorio'),
        department=SimpleNamespace(name='Centro de operaciones'), responsible=SimpleNamespace(name='Operador ficticio'),
        incident_type=SimpleNamespace(name='Intermitencia de transporte'), provider=SimpleNamespace(name='Proveedor ficticio'),
        description='Se detectaron pérdidas intermitentes de conectividad.\nEl NOC inició el diagnóstico del enlace.',
        resolution='Enlace estabilizado tras la intervención.\nSe verificó la recuperación del servicio.',
    )


def assert_page_size(data, size):
    boxes = re.findall(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]', data)
    assert boxes
    for width, height in boxes:
        assert float(width) == pytest.approx(size[0], abs=.01)
        assert float(height) == pytest.approx(size[1], abs=.01)


def test_legacy_layout_remains_landscape_and_modular_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    documents.fonts()
    for modular in (False, True):
        output = BytesIO()
        documents.build_pdf(output, 'Documento de prueba', 'America/Guatemala',
            [documents.paragraph('Contenido')], modular=modular, reference='DEMO-42', issued_at='22/10/2026 12:00')
        data = output.getvalue()
        assert_page_size(data, A4 if modular else (A4[1], A4[0]))
        assert (b'/Subtype /Image' in data) == modular


def test_modular_metadata_escapes_values_and_keeps_odd_field(rendered):
    documents.fonts()
    rows = [('Etiqueta <&>', 'Valor <tag> & texto\nOtra línea'), ('Nodo', 'NOC'), ('Final', 'CAMPO-IMPAR')]
    output = BytesIO()
    documents.build_pdf(output, 'Prueba', 'UTC', [documents.metadata_modules(rows)], modular=True, reference='DEMO')
    words = ' '.join(text for _, text in rendered)
    for value in ('Etiqueta <&>', 'Valor <tag> & texto', 'Otra línea', 'CAMPO-IMPAR'):
        assert value in words


def test_modular_heading_can_split_without_constructor_errors():
    documents.fonts()
    heading = documents.ModularHeading('Encabezado extenso ' * 100, accent=documents.PURPLE)
    heading.wrap(documents.MODULAR_WIDTH, documents.MODULAR_HEIGHT)
    fragments = heading.split(documents.MODULAR_WIDTH, 45)
    assert len(fragments) > 1
    assert all(part.accent == documents.PURPLE for part in fragments)


@pytest.mark.parametrize('scenario', ['interno-breve', 'interno-extenso', 'cliente-publico', 'cliente-sin-contenido', 'noc-completo', 'noc-multipagina'])
def test_fictitious_documents(scenario, tmp_path, monkeypatch, rendered):
    ticket = sample_ticket()
    headings = {}
    original_heading_draw = documents.ModularHeading.draw
    def capture_heading(self):
        headings[self.getPlainText()] = self.accent
        return original_heading_draw(self)
    monkeypatch.setattr(documents.ModularHeading, 'draw', capture_heading)
    entries = []
    original_entry_draw = documents.TimelineEntry.draw
    def capture_entry(self):
        if self.starts_entry:
            entries.append((self.accent, self.header.getPlainText()))
        return original_entry_draw(self)
    monkeypatch.setattr(documents.TimelineEntry, 'draw', capture_entry)
    long = scenario in {'interno-extenso', 'noc-multipagina'}
    if long:
        ticket.title = ('Incidencia de transporte con afectación intermitente y diagnóstico coordinado. ' * 8).strip()
        ticket.description = '\n'.join(f'DIAGNOSTICO-{n:03} Comprobación técnica con acentos áéíóú y símbolos & <NOC>.' for n in range(70))
    updates = [SimpleNamespace(occurred_at=ticket.start_at + timedelta(minutes=i * 5),
        responsible=ticket.responsible, visibility='PUBLIC' if not scenario.startswith('noc') and i % 2 else 'INTERNAL', escalation_id=None,
        content='\n'.join(f'PASO-{i:02}-{n:03} Medición del enlace y validación operativa.' for n in range(90 if long and i == 0 else 2)))
        for i in range(8 if long else 2)]
    escalation = SimpleNamespace(id=7, recipient=ticket.responsible, status='FINISHED',
        recipient_department_name='Ingeniería de transporte', recipient_position_name='Ingeniería N3', recipient_level=None,
        reason=SimpleNamespace(name='Diagnóstico especializado'), started_at=ticket.start_at,
        finished_at=ticket.end_at, description='Revisión de la ruta de transporte y verificación de recuperación.')
    monkeypatch.setattr(ticket_reports, 'get_ticket', lambda *_: ticket)
    monkeypatch.setattr(ticket_reports, 'list_updates', lambda *_: updates)
    monkeypatch.setattr(ticket_reports, 'list_escalations', lambda *_: [escalation])
    output = BytesIO()
    if scenario.startswith('cliente'):
        empty = scenario == 'cliente-sin-contenido'
        public = ticket_reports.CustomerReport(ticket.reference, ticket.title, ticket.customer.name,
            ticket.circuit.circuit_code, ticket.start_at, ticket.end_at, ticket.status,
            None if empty else 'Se presentó una intermitencia del servicio.\nSe inició la revisión.',
            None if empty else 'El servicio fue restablecido y verificado.',
            [] if empty else [ticket_reports.PublicIntervention(ticket.start_at + timedelta(minutes=30), 'Se iniciaron las verificaciones del servicio.'), ticket_reports.PublicIntervention(ticket.end_at, 'Se confirmó la estabilidad del enlace.')])
        monkeypatch.setattr(ticket_reports, 'customer_report', lambda *_: public)
        # Public composition must never request the complete ORM ticket.
        monkeypatch.setattr(ticket_reports, 'get_ticket', lambda *_: pytest.fail('Acceso al ORM privado'))
        ticket_reports.customer_pdf(None, 42, output, ZoneInfo('America/Guatemala'), ticket.end_at)
    elif scenario.startswith('noc'):
        ticket.reference = 'INT-DEMO-000042'
        monkeypatch.setattr(internal_ticket_reports, 'get_or_404', lambda *_: ticket)
        monkeypatch.setattr(internal_ticket_reports, 'list_updates', lambda *_, **__: updates)
        monkeypatch.setattr(internal_ticket_reports, 'list_escalations', lambda *_, **__: [escalation])
        session = SimpleNamespace(scalar=lambda *_: 3, execute=lambda *_: [
            (f'CLI-DEMO-{i:03}', 'Cliente ficticio', f'Incidencia relacionada {i}', 'CLOSED') for i in range(3)])
        internal_ticket_reports.internal_ticket_pdf(session, 42, output, ZoneInfo('America/Guatemala'), ticket.end_at)
    else:
        ticket_reports.internal_pdf(None, 42, output, ZoneInfo('America/Guatemala'), ticket.end_at)
    data = output.getvalue()
    (tmp_path / f'{scenario}.pdf').write_bytes(data)
    assert data.startswith(b'%PDF-') and data.rstrip().endswith(b'%%EOF')
    assert_page_size(data, A4)
    assert b'/Subtype /Image' in data
    assert headings['Resolución' if scenario.startswith('cliente') else 'Resolución documentada'] == documents.EMERALD
    assert headings['Descripción del incidente' if scenario.startswith('cliente') else 'Descripción original'] == documents.BLUE
    assert headings['Seguimiento público · Cronológico' if scenario.startswith('cliente') else 'Seguimiento cronológico · Uso interno'] == (documents.BLUE if scenario.startswith('cliente') else documents.CYAN)
    if not scenario.startswith('cliente'):
        assert headings['Historial de escalamientos'] == documents.AMBER
    if scenario.startswith('cliente'):
        assert len(entries) == (0 if scenario == 'cliente-sin-contenido' else 2)
        assert all(color == documents.BLUE for color, _ in entries)
        assert all('Pública' not in header and 'Interna' not in header and 'Operador' not in header for _, header in entries)
    else:
        assert len(entries) == len(updates)
        if scenario.startswith('noc'):
            assert all(color == documents.CYAN and 'Pública' not in header and 'Interna' not in header for color, header in entries)
        else:
            assert {color for color, _ in entries} == {documents.CYAN, documents.EMERALD}
    if scenario == 'interno-breve':
        assert len(re.findall(rb'/Type\s*/Page\b', data)) == 1
    words = ' '.join(text for _, text in rendered)
    assert ticket.reference in words and 'Página 1 /' in words and 'Zona horaria:' in words
    if long:
        assert any(page == 1 and 'DIAGNOSTICO-000' in text for page, text in rendered)
        assert 'DIAGNOSTICO-069' in words and 'PASO-00-089' in words
        assert max(page for page, _ in rendered) > 1
    if scenario.startswith('noc'):
        related_heading_page = next(page for page, text in rendered if 'Tickets de clientes relacionados' in text)
        first_related_page = next(page for page, text in rendered if 'CLI-DEMO-000' in text)
        assert related_heading_page == first_related_page
    if scenario.startswith('cliente'):
        for private in ('Operador ficticio', 'Nodo de laboratorio', 'Proveedor ficticio', 'Ingeniería', 'Escalamiento', 'PASO-'):
            assert private not in words
    path = tmp_path / f'{scenario}.pdf'
    path.write_bytes(data)
    print(f'PDF ficticio: {path}')


@pytest.mark.parametrize('status, label, color', [
    ('OPEN', 'Abierto · En curso', documents.AMBER),
    ('CLOSED', 'Cerrado', documents.EMERALD),
])
def test_identification_state_capsule_has_text_and_semantic_color(status, label, color, rendered):
    documents.fonts()
    capsule = documents.StateCapsule(status)
    assert capsule.label == label and capsule.color == color
    output = BytesIO()
    documents.build_pdf(output, 'Estado', 'UTC', [documents.identification('DEMO', 'Título', status, 'Reporte', '22/10/2026')], modular=True)
    assert label in ' '.join(text for _, text in rendered)


def test_related_incident_keeps_purple_accent(monkeypatch):
    ticket = sample_ticket()
    ticket.internal_ticket_id = 17
    monkeypatch.setattr(ticket_reports, 'get_ticket', lambda *_: ticket)
    monkeypatch.setattr(ticket_reports, 'list_updates', lambda *_: [])
    monkeypatch.setattr(ticket_reports, 'list_escalations', lambda *_: [])
    monkeypatch.setattr(ticket_reports, 'related_internal_incident', lambda *_: SimpleNamespace(
        reference='INT-DEMO', title='Incidencia relacionada', description='', sector='Sector', node=None, status='OPEN', provider=None))
    seen = {}
    original = documents.ModularHeading.draw
    def capture(self):
        seen[self.getPlainText()] = self.accent
        return original(self)
    monkeypatch.setattr(documents.ModularHeading, 'draw', capture)
    ticket_reports.internal_pdf(None, 42, BytesIO(), ZoneInfo('UTC'), ticket.end_at)
    assert seen['Incidencia interna relacionada'] == documents.PURPLE


@pytest.mark.parametrize('metadata', [{'responsible': 'PRIVADO'}, {'label': 'Pública'}, {'association': 'Escalamiento #1'}])
def test_customer_timeline_refuses_private_metadata(metadata):
    documents.fonts()
    with pytest.raises(ValueError, match='solo admite fecha y contenido'):
        documents.timeline_entry('22/10/2026', 'Contenido público', variant='customer', **metadata)


def test_long_timeline_splits_without_repeating_marker_or_metadata(monkeypatch, rendered):
    from reportlab.pdfgen.canvas import Canvas
    documents.fonts()
    circles = []
    original = Canvas.circle
    def capture(self, x, y, radius, *args, **kwargs):
        if radius == 2.7:
            circles.append(self._pageNumber)
        return original(self, x, y, radius, *args, **kwargs)
    monkeypatch.setattr(Canvas, 'circle', capture)
    date = '22/10/2026 12:00:00 -0600'
    content = '\n'.join(f'LINEA-TIMELINE-{i:03} & <literal> ' + ('IDENTIFICADORLARGO' * 4) for i in range(140))
    entry = documents.timeline_entry(date, content, responsible='Operador ficticio', label='Interna')
    fragments = entry.split(documents.MODULAR_WIDTH, 100)
    assert len(fragments) == 2
    assert fragments[0].starts_entry and not fragments[1].starts_entry
    assert fragments[0].wrap(documents.MODULAR_WIDTH, 100)[1] <= 100
    output = BytesIO()
    documents.build_pdf(output, 'Cronología extensa', 'UTC', [entry], modular=True, reference='DEMO-LARGO')
    words = ' '.join(text for _, text in rendered)
    assert words.count(date) == 1 and len(circles) == 1
    for i in range(140):
        assert f'LINEA-TIMELINE-{i:03}' in words
    assert '<literal>' in words
    assert max(page for page, _ in rendered) >= 3


def test_timeline_cannot_leave_a_header_and_marker_without_content():
    documents.fonts()
    entry = documents.timeline_entry('22/10/2026 12:00', 'Contenido\nSegunda línea', responsible='Operador')
    header_height = entry.header.wrap(documents.MODULAR_WIDTH - 38, 100)[1]
    assert entry.split(documents.MODULAR_WIDTH, header_height + 6) == []
