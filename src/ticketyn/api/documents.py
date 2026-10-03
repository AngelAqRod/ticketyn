"""Elementos visuales compartidos para los documentos PDF de Ticketyn."""
from functools import partial
from html import escape
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor('#102744')
BLUE = colors.HexColor('#1e60d8')
SOFT = colors.HexColor('#edf3fc')
BORDER = colors.HexColor('#dce5f1')
MUTED = colors.HexColor('#526883')
FONT, BOLD = 'TicketynVera', 'TicketynVeraBold'


def fonts():
    # Ambas fuentes están incluidas en ReportLab, sin descargas ni fuentes del SO.
    directory = Path(reportlab.__file__).parent / 'fonts'
    for name, filename in [(FONT, 'Vera.ttf'), (BOLD, 'VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(directory / filename)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def paragraph(value, *, size=8, color=NAVY, bold=False, keep=False):
    style = ParagraphStyle('ticketyn', fontName=BOLD if bold else FONT, fontSize=size,
        leading=size * 1.4, textColor=color, spaceAfter=5, keepWithNext=keep,
        splitLongWords=True, wordWrap='CJK')
    return Paragraph(escape(str(value if value is not None else '—')).replace('\n', '<br/>'), style)


def section(title, number=None, *, keep=True):
    return paragraph(f'{number:02} / {title}' if number else title, size=11, bold=True, keep=keep)


def analytical_block(heading, graphic, table, width):
    """Keep a measured small section together, leaving large tables splittable.

    Reserve the same header/footer margins and frame padding as build_pdf.
    Measure wrapped labels too: row count alone is not a reliable size limit.
    """
    heading.style.keepWithNext = False
    items = [heading, *([graphic] if graphic is not None else []), table]
    available_height = landscape(A4)[1] - 90 - 43 - 12
    height = sum(item.wrap(width, available_height)[1]
                 + item.getSpaceBefore() + item.getSpaceAfter() for item in items)
    if height <= available_height:
        return [KeepTogether(items)]
    # Only the heading and chart travel together; LongTable retains repeatRows.
    return [KeepTogether(items[:-1]), table] if graphic is not None else [heading, table]


class NumberedCanvas(Canvas):
    def __init__(self, *args, document_title, zone, **kwargs):
        super().__init__(*args, **kwargs)
        self.states = []
        self.document_title, self.zone = document_title, zone
        self.setTitle(f'Ticketyn — {document_title}')
        self.setAuthor('Ticketyn')

    def showPage(self):
        self.states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self.states)
        for state in self.states:
            self.__dict__.update(state)
            self.chrome(total)
            super().showPage()
        super().save()

    def chrome(self, total):
        width, height = self._pagesize
        self.saveState()
        self.setFillColor(NAVY)
        self.rect(0, height - 72, width, 72, fill=1, stroke=0)
        self.setFillColor(BLUE)
        self.rect(0, height - 72, 8, 72, fill=1, stroke=0)
        self.setFillColor(colors.white)
        self.setFont(BOLD, 17)
        self.drawString(30, height - 29, 'Ticketyn')
        self.setFont(FONT, 7)
        self.drawString(30, height - 44, 'GESTIÓN DE INCIDENCIAS')
        self.setFont(BOLD, 10)
        self.drawRightString(width - 30, height - 30, self.document_title)
        self.setFont(FONT, 7)
        self.drawRightString(width - 30, height - 46, f'Zona horaria: {self.zone}')
        self.setStrokeColor(BORDER)
        self.line(30, 31, width - 30, 31)
        self.setFillColor(MUTED)
        self.setFont(FONT, 7)
        self.drawString(30, 19, f'Ticketyn · {self.document_title}')
        self.drawRightString(width - 30, 19, f'Página {self._pageNumber} / {total}')
        self.restoreState()


def build_pdf(output, title, zone, story):
    fonts()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=30,
        leftMargin=30, topMargin=90, bottomMargin=43, pageCompression=1)
    document.build(story, canvasmaker=partial(NumberedCanvas, document_title=title, zone=zone))


def modern_table(headers, rows, widths, *, reference=False):
    data = [[paragraph(value, color=colors.white, bold=True, size=7) for value in headers]]
    for row in rows:
        data.append([paragraph(value, size=7, bold=reference and index == 0,
                               color=BLUE if reference and index == 0 else NAVY)
                     for index, value in enumerate(row)])
    if len(data) == 1:
        data.append([paragraph('Sin resultados.' if index == 0 else '') for index in range(len(headers))])
    table = LongTable(data, colWidths=widths, repeatRows=1, splitInRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SOFT]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LINEBELOW', (0, 0), (-1, 0), .5, BLUE),
        ('LINEBELOW', (0, 1), (-1, -1), .25, BORDER),
    ]))
    return table


def metric_strip(items, width):
    columns = [[paragraph(label, color=colors.HexColor('#b8cde8'), size=7),
                paragraph(value, color=colors.white, size=16, bold=True)] for label, value in items]
    table = Table([columns], colWidths=[width / len(items)] * len(items), hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('TOPPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 13), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    return table


class TrendGraphic(Flowable):
    """Gráfica vectorial indivisible; datos y buckets proporcionados por el motor."""
    def __init__(self, buckets, zone, width, grain):
        super().__init__()
        self.buckets, self.zone, self.width, self.grain = buckets, zone, width, grain
        self.height = 125

    def draw(self):
        c, left, right, base, top = self.canv, 24, self.width - 10, 25, 108
        maximum = max((bucket.count for bucket in self.buckets), default=0) or 1
        c.setFont(FONT, 7)
        for index in range(5):
            y = base + (top - base) * index / 4
            c.setStrokeColor(BORDER); c.setLineWidth(.4); c.line(left, y, right, y)
            c.setFillColor(MUTED); c.drawRightString(left - 5, y - 2, f'{maximum * index / 4:g}')
        points = [(left + index * (right - left) / max(1, len(self.buckets) - 1),
                   base + bucket.count * (top - base) / maximum) for index, bucket in enumerate(self.buckets)]
        c.setStrokeColor(BLUE); c.setLineWidth(1.8)
        for previous, current in zip(points, points[1:]): c.line(*previous, *current)
        if len(points) == 1:
            c.setFillColor(BLUE); c.circle(*points[0], 2, fill=1, stroke=0)
        c.setFillColor(MUTED)
        if self.buckets:
            c.drawString(left, 10, self.buckets[0].start_at.astimezone(self.zone).strftime('%d/%m/%Y %H:%M'))
            grain = {'hour': 'hora', 'day': 'día', 'week': 'semana', 'month': 'mes'}.get(self.grain, self.grain)
            c.drawCentredString(self.width / 2, 10, f'Agrupación: {grain}')
            c.drawRightString(right, 10, self.buckets[-1].start_at.astimezone(self.zone).strftime('%d/%m/%Y %H:%M'))


def ticket_pdf_table(rows, zone, width):
    def values():
        for ticket, customer, circuit, sector, department, kind in rows:
            date = lambda value: value.astimezone(zone).strftime('%d/%m/%Y\n%H:%M') if value else '—'
            yield [ticket.reference, 'Abierto' if ticket.status == 'OPEN' else 'Cerrado', ticket.title,
                   f'{customer.customer_code}\n{customer.name}', circuit.circuit_code, circuit.node.name if circuit.node else "Sin asignar", ticket.responsible.name if ticket.responsible else "Sin asignar", sector.name,
                   kind.name, date(ticket.start_at), f'{date(ticket.end_at)}\n{duration_text(ticket.duration_seconds) if ticket.duration_seconds is not None else "En curso"}']
    return modern_table(['Referencia', 'Estado', 'Título', 'Cliente', 'Circuito', 'Nodo', 'Responsable', 'Sector', 'Tipo', 'Inicio', 'Fin / Duración'],
        values(), [width * fraction for fraction in [.10, .06, .115, .115, .105, .075, .085, .07, .075, .10, .10]], reference=True)


def duration_text(seconds):
    if seconds is None: return '—'
    seconds = int(seconds)
    if seconds < 60: return f'{seconds} s'
    minutes = seconds // 60
    days, hours = divmod(minutes // 60, 24)
    return ' '.join(part for part in [f'{days} d' if days else '', f'{hours} h' if hours else '', f'{minutes % 60} min' if minutes % 60 else ''] if part)


class BarsGraphic(Flowable):
    """Barras vectoriales; los rankings conservan su tabla completa."""
    def __init__(self, rows, width, value_field='count', limit=10):
        super().__init__()
        self.rows = list(rows)[:limit]
        self.width = width
        self.value_field = value_field
        self.row_height = min(22, 380 / max(1, len(self.rows)))
        self.height = max(45, self.row_height * len(self.rows) + 12)

    def draw(self):
        canvas = self.canv
        maximum = max((getattr(row, self.value_field) for row in self.rows), default=0) or 1
        label_width = self.width * .42
        for index, row in enumerate(self.rows):
            y = self.height - self.row_height * (index + 1)
            canvas.setFont(FONT, 8)
            canvas.setFillColor(NAVY)
            label = row.label
            while canvas.stringWidth(label, FONT, 8) > label_width - 15:
                label = label[:-2] + '…'
            canvas.drawString(0, y, label)
            value = getattr(row, self.value_field)
            canvas.setFillColor(BLUE)
            canvas.rect(label_width, y - 2, (self.width - label_width - 65) * value / maximum, 9, fill=1, stroke=0)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(self.width, y, duration_text(value) if self.value_field == 'average_duration_seconds' else str(value))


class ActivityGraphic(TrendGraphic):
    def draw(self):
        canvas = self.canv
        left, right, base, top = 28, self.width - 10, 25, 108
        maximum = max((max(row.started, row.closed) for row in self.buckets), default=0) or 1
        canvas.setFont(FONT, 7)
        for index in range(5):
            y = base + (top - base) * index / 4
            canvas.setStrokeColor(BORDER); canvas.setLineWidth(.4); canvas.line(left, y, right, y)
            canvas.setFillColor(MUTED); canvas.drawRightString(left - 5, y - 2, f'{maximum * index / 4:g}')
        for field, color, label, x in [('started', BLUE, 'Iniciadas', left), ('closed', MUTED, 'Cerradas', left + 95)]:
            canvas.setFillColor(color); canvas.drawString(x, 115, label)
            points = [(left + index * (right - left) / max(1, len(self.buckets) - 1), base + getattr(row, field) * (top - base) / maximum) for index, row in enumerate(self.buckets)]
            canvas.setStrokeColor(color); canvas.setLineWidth(1.5)
            for previous, current in zip(points, points[1:]): canvas.line(*previous, *current)
            if len(points) == 1: canvas.circle(*points[0], 2, fill=1, stroke=0)
        if self.buckets:
            canvas.setFillColor(MUTED)
            canvas.drawString(left, 10, self.buckets[0].start_at.astimezone(self.zone).strftime('%d/%m %H:%M'))
            canvas.drawRightString(right, 10, self.buckets[-1].start_at.astimezone(self.zone).strftime('%d/%m %H:%M'))
