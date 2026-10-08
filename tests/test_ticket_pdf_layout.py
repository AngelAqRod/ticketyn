"""Real ReportLab pagination regressions without a database or production data."""
from datetime import datetime, timezone, timedelta
from io import BytesIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from reportlab.pdfgen.textobject import PDFTextObject
from reportlab.pdfgen.canvas import Canvas

from ticketyn.api import ticket_reports as reports


@pytest.fixture
def rendered(monkeypatch):
    entries = []
    original = PDFTextObject._textOut

    def capture(self, text, *args, **kwargs):
        entries.append((self._canvas._pageNumber, text))
        return original(self, text, *args, **kwargs)

    monkeypatch.setattr(PDFTextObject, '_textOut', capture)
    def capture_canvas(original):
        def draw(self, x, y, text, *args, **kwargs):
            entries.append((self._pageNumber, text))
            return original(self, x, y, text, *args, **kwargs)
        return draw
    for method in ['drawString', 'drawRightString']:
        monkeypatch.setattr(Canvas, method, capture_canvas(getattr(Canvas, method)))
    return entries


def incident():
    now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    return SimpleNamespace(reference='TEST-0000004', title='Interrupción del servicio de Internet',
        customer=SimpleNamespace(name='Cliente de prueba', customer_code='C-001'),
        circuit=SimpleNamespace(circuit_code='CIR-001'), node=None,
        sector=SimpleNamespace(name='Sector de prueba'), department=SimpleNamespace(name='Departamento de prueba'),
        responsible=SimpleNamespace(name='RESPONSABLE-PRIVADO'), incident_type=SimpleNamespace(name='TIPO-PRIVADO'),
        status='CLOSED', start_at=now - timedelta(hours=2), end_at=now,
        description='Descripción original.', resolution=None)


def render_internal(monkeypatch, updates):
    ticket = incident()
    monkeypatch.setattr(reports, 'get_ticket', lambda *_: ticket)
    monkeypatch.setattr(reports, 'list_updates', lambda *_: updates)
    output = BytesIO()
    reports.internal_pdf(None, 1, output, ZoneInfo('UTC'), ticket.end_at)
    return output.getvalue()


def intervention(content, minutes=0):
    return SimpleNamespace(content=content, occurred_at=incident().end_at + timedelta(minutes=minutes),
        responsible=SimpleNamespace(name='Operador de prueba'), visibility='INTERNAL')


def test_short_history_starts_on_first_page(monkeypatch, rendered):
    data = render_internal(monkeypatch, [intervention('PRIMERA-INTERVENCION\nSegunda línea de diagnóstico.'), intervention('SEGUNDA-INTERVENCION', 10)])
    assert data.startswith(b'%PDF-')
    assert any(page == 1 and 'SEGUNDA-INTERVENCION' in text for page, text in rendered)
    assert any(page == 1 and 'PRIMERA-INTERVENCION' in text for page, text in rendered)
    assert any(page == 1 and 'Seguimiento cronológico' in text for page, text in rendered)
    assert sum('Interrupción del servicio de Internet' in text for _, text in rendered) == 1


def test_long_first_intervention_starts_here_and_continues(monkeypatch, rendered):
    content = '\n'.join(f'LINEA-{number:03} Texto de intervención extenso.' for number in range(100))
    data = render_internal(monkeypatch, [intervention(content)])
    assert any(page == 1 and 'LINEA-000' in text for page, text in rendered)
    assert any(page > 1 and 'LINEA-099' in text for page, text in rendered)
    assert b'%%EOF' in data
    positions = [next(index for index, (_, text) in enumerate(rendered) if f'LINEA-{number:03}' in text) for number in range(100)]
    assert positions == sorted(positions)


def test_small_interventions_keep_metadata_and_content_together(monkeypatch, rendered):
    render_internal(monkeypatch, [intervention(f'CONTENIDO-{number:02}', number) for number in range(20)])
    pages = max(page for page, _ in rendered)
    assert pages > 1
    for page in range(1, pages + 1):
        page_text = ' '.join(text for number, text in rendered if number == page)
        assert 'Ticketyn' in page_text and 'Reporte técnico interno' in page_text
        assert f'Página {page} / {pages}' in page_text and 'Emitido:' in page_text
    for number in range(20):
        date = reports.date_text(incident().end_at + timedelta(minutes=number), ZoneInfo('UTC'))
        metadata_page = next(page for page, text in rendered if date in text and 'Operador' in text)
        content_page = next(page for page, text in rendered if f'CONTENIDO-{number:02}' in text)
        assert metadata_page == content_page


def test_customer_title_without_internal_classification(monkeypatch, rendered):
    ticket = incident()
    public = reports.CustomerReport(reference=ticket.reference, title=ticket.title,
        customer_name=ticket.customer.name, circuit_code=ticket.circuit.circuit_code,
        start_at=ticket.start_at, end_at=ticket.end_at, status=ticket.status,
        customer_description=None, customer_resolution=None,
        interventions=[reports.PublicIntervention(ticket.end_at, 'CONTENIDO-PUBLICO')])
    monkeypatch.setattr(reports, 'customer_report', lambda *_: public)
    reports.customer_pdf(None, 1, BytesIO(), ZoneInfo('UTC'), ticket.end_at)
    words = ' '.join(text for _, text in rendered)
    assert words.count(ticket.title) == 1
    assert words.index(ticket.reference) < words.index(ticket.title) < words.index('Identificación')
    assert 'CONTENIDO-PUBLICO' in words
    for private in ['TIPO-PRIVADO', 'RESPONSABLE-PRIVADO', 'Tipo de incidencia', 'Responsable', 'Descripción original.']:
        assert private not in words
