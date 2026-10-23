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
PURPLE = colors.HexColor('#7c3aed')
EMERALD = colors.HexColor('#047857')
AMBER = colors.HexColor('#b45309')
CYAN = colors.HexColor('#0e7490')
MODULAR_MARGIN = 51
MODULAR_TOP = 88
MODULAR_BOTTOM = 56
MODULAR_WIDTH = A4[0] - 2 * MODULAR_MARGIN - 12
MODULAR_HEIGHT = A4[1] - MODULAR_TOP - MODULAR_BOTTOM - 12
FONT, BOLD = 'TicketynVera', 'TicketynVeraBold'


def fonts():
    # Ambas fuentes están incluidas en ReportLab, sin descargas ni fuentes del SO.
    directory = Path(reportlab.__file__).parent / 'fonts'
    for name, filename in [(FONT, 'Vera.ttf'), (BOLD, 'VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(directory / filename)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def paragraph(value, *, size=8, color=NAVY, bold=False, keep=False, space_after=5, word_wrap='CJK'):
    style = ParagraphStyle('ticketyn', fontName=BOLD if bold else FONT, fontSize=size,
        leading=size * 1.4, textColor=color, spaceAfter=space_after, keepWithNext=keep,
        splitLongWords=True, wordWrap=word_wrap)
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
    def __init__(self, *args, document_title, zone, issued_at=None, subtitle='GESTIÓN DE INCIDENCIAS', **kwargs):
        super().__init__(*args, **kwargs)
        self.states = []
        self.document_title, self.zone = document_title, zone
        self.issued_at = issued_at
        self.subtitle = subtitle
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
        self.drawString(30, height - 44, self.subtitle)
        self.setFont(BOLD, 10)
        self.drawRightString(width - 30, height - 30, self.document_title)
        self.setFont(FONT, 7)
        self.drawRightString(width - 30, height - 46, f'Zona horaria: {self.zone}')
        self.setStrokeColor(BORDER)
        self.line(30, 31, width - 30, 31)
        self.setFillColor(MUTED)
        self.setFont(FONT, 7)
        self.drawString(30, 19, f'Emitido: {self.issued_at}' if self.issued_at else f'Ticketyn · {self.document_title}')
        self.drawRightString(width - 30, 19, f'Página {self._pageNumber} / {total}')
        self.restoreState()


def branding_logo():
    root = Path(__file__).resolve().parents[3]
    for directory in ('frontend/dist/branding', 'frontend/public/branding'):
        logo = root / directory / 'logo_horizontal_claro.png'
        if logo.is_file():
            return logo
    raise FileNotFoundError('No se encontró el logotipo local de Ticketyn.')


class ModularCanvas(NumberedCanvas):
    def __init__(self, *args, reference, accent=BLUE, margin=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reference, self.accent = reference, accent
        self.margin = margin

    def chrome(self, total):
        width, height = self._pagesize
        is_landscape = width > height
        margin = self.margin if self.margin is not None else (30 if is_landscape else MODULAR_MARGIN)
        self.saveState()
        logo_y = height - 58 if is_landscape else height - 65
        self.drawImage(str(branding_logo()), margin, logo_y, width=112, height=35,
                       preserveAspectRatio=True, mask='auto')
        if is_landscape:
            self.setFont(BOLD, 10.5)
            self.setFillColor(self.accent)
            self.drawRightString(width - margin, height - 37, self.document_title)
            if self.subtitle:
                self.setFont(FONT, 7)
                self.setFillColor(MUTED)
                self.drawRightString(width - margin, height - 49, self.subtitle)
        else:
            heading = paragraph(self.document_title, size=9, color=self.accent, bold=True, space_after=0)
            heading.style.alignment = 2
            _, h = heading.wrap(width - 2 * margin - 145, 50)
            heading.drawOn(self, margin + 145, height - 39 - h)
        header_line_y = height - 68 if is_landscape else height - 78
        self.setStrokeColor(self.accent)
        self.setLineWidth(.8)
        self.line(margin, header_line_y, width - margin, header_line_y)
        footer_line_y = 44 if is_landscape else 48
        self.setStrokeColor(BORDER)
        self.setLineWidth(.4)
        self.line(margin, footer_line_y, width - margin, footer_line_y)
        ref_text = f'Ticketyn · {self.reference}' if self.reference else 'Ticketyn'
        reference = paragraph(ref_text, size=7, color=MUTED, space_after=0)
        _, h = reference.wrap(width - 2 * margin - 100, 30)
        reference.drawOn(self, margin, (35 - h) if is_landscape else (39 - h))
        issued_text = f'Emitido: {self.issued_at} · Zona horaria: {self.zone}' if self.issued_at else f'Zona horaria: {self.zone}'
        issued = paragraph(issued_text, size=6.5, color=MUTED, space_after=0)
        _, h = issued.wrap(width - 2 * margin - 100, 30)
        issued.drawOn(self, margin, (21 - h) if is_landscape else (23 - h))
        self.setFont(FONT, 7)
        self.setFillColor(MUTED)
        self.drawRightString(width - margin, 26 if is_landscape else 29, f'Página {self._pageNumber} / {total}')
        self.restoreState()


def build_pdf(output, title, zone, story, *, issued_at=None, subtitle='GESTIÓN DE INCIDENCIAS',
              modular=False, reference='', accent=BLUE, landscape_mode=False, pagesize=None):
    fonts()
    if modular:
        if landscape_mode or (pagesize is not None and pagesize[0] > pagesize[1]):
            size = pagesize or landscape(A4)
            margin = 30
            top_margin = 78
            bottom_margin = 52
            document = SimpleDocTemplate(output, pagesize=size, rightMargin=margin,
                leftMargin=margin, topMargin=top_margin, bottomMargin=bottom_margin, pageCompression=1)
            canvas = partial(ModularCanvas, reference=reference, accent=accent, margin=margin)
        else:
            document = SimpleDocTemplate(output, pagesize=A4, rightMargin=MODULAR_MARGIN,
                leftMargin=MODULAR_MARGIN, topMargin=MODULAR_TOP, bottomMargin=MODULAR_BOTTOM, pageCompression=1)
            canvas = partial(ModularCanvas, reference=reference, accent=accent)
    else:
        document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=30,
            leftMargin=30, topMargin=90, bottomMargin=43, pageCompression=1)
        canvas = NumberedCanvas
    document.build(story, canvasmaker=partial(canvas, document_title=title, zone=zone, issued_at=issued_at, subtitle=subtitle))


class ModularHeading(Paragraph):
    def __init__(self, value, style=None, bulletText=None, frags=None, *, accent=BLUE, size=10.5, keep=True):
        style = style or ParagraphStyle('modular-heading', fontName=BOLD, fontSize=size, leading=size * 1.4,
            textColor=NAVY, leftIndent=10, spaceBefore=5, spaceAfter=3, keepWithNext=keep)
        self.accent = getattr(style, 'modular_accent', accent)
        style.modular_accent = self.accent
        super().__init__(escape(str(value)) if value is not None else None, style, bulletText=bulletText, frags=frags)

    def draw(self):
        super().draw()
        self.canv.saveState()
        self.canv.setStrokeColor(self.accent)
        self.canv.setLineWidth(2)
        self.canv.line(1, 1, 1, self.height - 1)
        self.canv.restoreState()


class StateCapsule(Flowable):
    def __init__(self, status, *, label=None, color=None, background=None):
        super().__init__()
        if label is not None:
            self.label = label
            self.color = color or EMERALD
            self.background = background or colors.HexColor('#ecfdf5')
        elif status == 'OPEN':
            self.label = 'Abierto · En curso'
            self.color = AMBER
            self.background = colors.HexColor('#fff7e6')
        elif status in ('CLOSED', 'RESOLVED'):
            self.label = 'Cerrado'
            self.color = EMERALD
            self.background = colors.HexColor('#ecfdf5')
        elif status in ('ACTIVE', 'ACTIVA'):
            self.label = 'Activa'
            self.color = EMERALD
            self.background = colors.HexColor('#ecfdf5')
        else:
            self.label = str(status) if status else 'Registrada'
            self.color = color or EMERALD
            self.background = background or colors.HexColor('#ecfdf5')
        self.width = pdfmetrics.stringWidth(self.label, BOLD, 7.5) + 16
        self.height = 18

    def draw(self):
        self.canv.setFillColor(self.background)
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(.4)
        self.canv.roundRect(0, 0, self.width, self.height, 8, fill=1, stroke=1)
        self.canv.setFillColor(self.color)
        self.canv.setFont(BOLD, 7.5)
        self.canv.drawString(8, 6, self.label)


class MetadataCard(Paragraph):
    """Draw each cell independently; Paragraph keeps long values splittable."""
    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(colors.white)
        self.canv.setStrokeColor(BORDER)
        self.canv.setLineWidth(.4)
        self.canv.roundRect(-7, -3, self.width + 14, self.height + 6, 4, fill=1, stroke=1)
        self.canv.restoreState()
        super().draw()


def identification(reference, title, status, classification, date, *, accent=BLUE,
                   capsule_label=None, capsule_color=None):
    capsule = StateCapsule(status, label=capsule_label, color=capsule_color)
    bg = colors.HexColor('#ecfdf5') if accent == EMERALD else (colors.HexColor('#faf5ff') if accent == PURPLE else SOFT)
    status_row = Table([[capsule, paragraph(date, size=7.5, color=MUTED, space_after=0)]],
        colWidths=[capsule.width + 12, MODULAR_WIDTH - 28 - capsule.width - 12], hAlign='LEFT')
    status_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    table = LongTable([
        [paragraph(classification, size=7, color=accent, bold=True, space_after=0)],
        [paragraph(reference, size=21, bold=True, space_after=0)],
        [paragraph(title, size=12, space_after=0)],
        [status_row],
    ], colWidths=[MODULAR_WIDTH], splitInRow=1, hAlign='LEFT', cornerRadii=[6, 6, 6, 6])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, 0), 9), ('BOTTOMPADDING', (0, -1), (-1, -1), 9),
        ('LINEBEFORE', (0, 0), (0, -1), 4, accent),
    ]))
    table.spaceAfter = 8
    return table


def metadata_modules(rows):
    def cell(row):
        label, value = row
        value = '—' if value is None else str(value)
        text = f'<font size="7" color="{MUTED.hexval()}">{escape(str(label))}</font><br/>{escape(value).replace(chr(10), "<br/>")}'
        return MetadataCard(text, ParagraphStyle('metadata', fontName=FONT, fontSize=9,
            leading=10.5, textColor=NAVY, wordWrap='CJK', splitLongWords=True))
    rows = list(rows)
    data = [[cell(rows[i]), '', cell(rows[i + 1]) if i + 1 < len(rows) else ''] for i in range(0, len(rows), 2)]
    table = LongTable(data, colWidths=[(MODULAR_WIDTH - 12) / 2, 12, (MODULAR_WIDTH - 12) / 2],
                      splitInRow=1, hAlign='LEFT')
    styles = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 9),
              ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 5),
              ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]
    table.setStyle(TableStyle(styles))
    table.spaceAfter = 6
    return table


class TimelineEntry(Flowable):
    """A splittable narrative card; continuation fragments never repeat the event."""
    def __init__(self, content, accent, *, header=None, section_heading=None, starts_entry=True):
        super().__init__()
        self.content, self.accent = content, accent
        self.header, self.section_heading, self.starts_entry = header, section_heading, starts_entry
        self.spaceBefore, self.spaceAfter = 1, 4

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.section_height = 0
        if self.section_heading is not None:
            _, height = self.section_heading.wrap(availWidth, availHeight)
            self.section_height = height + self.section_heading.getSpaceBefore() + self.section_heading.getSpaceAfter()
        _, height = self.content.wrap(availWidth - 38, max(0, availHeight - self.section_height - 6))
        self.height = self.section_height + height + 6
        return self.width, self.height

    def split(self, availWidth, availHeight):
        self.wrap(availWidth, availHeight)
        if self.height <= availHeight:
            return [self]
        available = availHeight - self.section_height - 6
        minimum = self.content.style.leading
        if self.starts_entry and self.header is not None:
            minimum += self.header.wrap(availWidth - 38, MODULAR_HEIGHT)[1]
        if available < min(minimum, MODULAR_HEIGHT / 2):
            return []
        fragments = self.content.split(availWidth - 38, available)
        if len(fragments) < 2:
            return []
        return [TimelineEntry(fragment, self.accent,
            header=self.header if index == 0 else None,
            section_heading=self.section_heading if index == 0 else None,
            starts_entry=self.starts_entry and index == 0)
            for index, fragment in enumerate(fragments)]

    def draw(self):
        canvas = self.canv
        card_height = self.height - self.section_height
        canvas.saveState()
        if self.section_heading is not None:
            self.section_heading.drawOn(canvas, 0,
                card_height + self.section_heading.getSpaceAfter())
        tint = colors.Color(*(1 - (1 - component) * .045 for component in
                              (self.accent.red, self.accent.green, self.accent.blue)))
        border = colors.Color(*(1 - (1 - component) * .22 for component in
                                (self.accent.red, self.accent.green, self.accent.blue)))
        canvas.setFillColor(tint)
        canvas.setStrokeColor(border)
        canvas.setLineWidth(.4)
        canvas.roundRect(20, 0, self.width - 20, card_height, 5, fill=1, stroke=1)
        canvas.setStrokeColor(self.accent)
        canvas.setLineWidth(.7)
        canvas.line(6, 0, 6, card_height)
        canvas.setLineWidth(1.5)
        canvas.line(20, 5, 20, card_height - 5)
        if self.starts_entry:
            canvas.setFillColor(self.accent)
            canvas.circle(6, card_height - 12, 2.7, fill=1, stroke=0)
        self.content.drawOn(canvas, 29, 3)
        canvas.restoreState()


def timeline_entry(date, content, *, responsible=None, label=None, association=None,
                   accent=CYAN, variant='internal', section_heading=None):
    if variant not in ('internal', 'customer'):
        raise ValueError('Variante de cronología no válida')
    if variant == 'customer':
        if responsible is not None or label is not None or association is not None:
            raise ValueError('La cronología de cliente solo admite fecha y contenido autorizado')
        accent = BLUE
    header = f'<font size="9"><b>{escape(str(date))}</b></font>'
    if responsible is not None:
        header += f' <font size="7.5" color="{MUTED.hexval()}">· {escape(str(responsible))}</font>'
    if label is not None:
        header += f' <font size="7" color="{accent.hexval()}"><b>· {escape(str(label))}</b></font>'
    if association is not None:
        header += f' <font size="7.5" color="{MUTED.hexval()}">· {escape(str(association))}</font>'
    style = ParagraphStyle('timeline', fontName=FONT, fontSize=10, leading=13,
        textColor=NAVY, wordWrap='CJK', splitLongWords=True)
    body = escape(str(content)).replace('\n', '<br/>')
    return TimelineEntry(Paragraph(header + '<br/>' + body, style), accent,
        header=Paragraph(header, style), section_heading=section_heading)


def report_identification(title, *, period=None, filters=None, total=None, accent=BLUE,
                          category='REPORTE OPERATIVO', width=None):
    width = width or (landscape(A4)[0] - 60)
    bg = colors.HexColor('#ecfdf5') if accent == EMERALD else (colors.HexColor('#faf5ff') if accent == PURPLE else SOFT)
    lines = [
        [paragraph(category.upper(), size=7, color=accent, bold=True, space_after=2)],
        [paragraph(title, size=14, bold=True, color=NAVY, space_after=3)],
    ]
    meta_parts = []
    if period:
        meta_parts.append(f'Período: {period}')
    if filters:
        meta_parts.append(f'Filtros: {filters}')
    if total is not None:
        meta_parts.append(f'Total encontrado: {total}')
    if meta_parts:
        meta_text = ' · '.join(meta_parts)
        lines.append([paragraph(meta_text, size=7.5, color=MUTED, space_after=0)])

    table = Table(lines, colWidths=[width], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 7),
        ('LINEBEFORE', (0, 0), (0, -1), 3.5, accent),
    ]))
    table.spaceAfter = 8
    return table


def modular_metric_strip(items, width, *, accent=BLUE):
    """Modern Modular metric cards strip for tabular and statistical reports.

    items: list of (label, value) or (label, value, color)
    """
    items = list(items)
    count = len(items)
    if count == 0:
        return Spacer(1, 0)
    spacing = 8
    total_spacing = spacing * (count - 1)
    card_width = (width - total_spacing) / count
    cards = []
    col_widths = []
    for index, item in enumerate(items):
        if len(item) == 3:
            label, value, color = item
        else:
            label, value = item
            color = accent
        card_content = [
            paragraph(str(label).upper(), size=6.5, color=MUTED, bold=True, space_after=2),
            paragraph(str(value if value is not None else '0'), size=14, color=color, bold=True, space_after=0),
        ]
        card = Table([[c] for c in card_content], colWidths=[card_width], hAlign='CENTER')
        card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEBEFORE', (0, 0), (0, -1), 2.5, color),
        ]))
        cards.append(card)
        col_widths.append(card_width)
        if index < count - 1:
            cards.append('')
            col_widths.append(spacing)

    row_table = Table([cards], colWidths=col_widths, hAlign='LEFT')
    row_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    row_table.spaceAfter = 8
    return row_table


def modern_table(headers, rows, widths, *, reference=False, compact=False, word_wrap='CJK',
                 light=False, accent=BLUE, status_colors=True):
    header_bg = (colors.HexColor('#ecfdf5') if accent == EMERALD else (colors.HexColor('#f5f3ff') if accent == PURPLE else SOFT)) if light else NAVY
    header_color = NAVY if light else colors.white
    row_bg = [colors.white, (colors.HexColor('#f0fdf4') if accent == EMERALD else (colors.HexColor('#faf5ff') if accent == PURPLE else colors.HexColor('#f8fafc')))] if light else [colors.white, SOFT]

    data = [[paragraph(value, color=header_color, bold=True, size=7.5 if light else 7,
                       space_after=0 if compact else 4, word_wrap=word_wrap) for value in headers]]
    for row in rows:
        row_cells = []
        for index, value in enumerate(row):
            str_val = str(value if value is not None else '')
            if status_colors and str_val == 'Abierto':
                cell_color = AMBER
                cell_bold = True
            elif status_colors and str_val == 'Cerrado':
                cell_color = EMERALD
                cell_bold = True
            elif status_colors and str_val == 'Incremento':
                cell_color = EMERALD
                cell_bold = True
            elif status_colors and str_val == 'Decremento':
                cell_color = colors.HexColor('#0284c7')
                cell_bold = True
            elif status_colors and str_val == 'Reactivación':
                cell_color = EMERALD
                cell_bold = True
            elif status_colors and str_val == 'Baja':
                cell_color = colors.HexColor('#475569')
                cell_bold = True
            elif reference and index == 0:
                cell_color = accent
                cell_bold = True
            else:
                cell_color = NAVY
                cell_bold = False
            row_cells.append(paragraph(value, size=7.5 if light else 7, bold=cell_bold,
                                       color=cell_color, space_after=0 if compact else 4, word_wrap=word_wrap))
        data.append(row_cells)
    if len(data) == 1:
        data.append([paragraph('Sin resultados.' if index == 0 else '') for index in range(len(headers))])
    table = LongTable(data, colWidths=widths, repeatRows=1, splitInRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), row_bg),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3 if compact else 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if compact else 5),
        ('LINEBELOW', (0, 0), (-1, 0), .75 if light else .5, accent if light else BLUE),
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
    def __init__(self, buckets, zone, width, grain, accent=BLUE):
        super().__init__()
        self.buckets, self.zone, self.width, self.grain, self.accent = buckets, zone, width, grain, accent
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
        c.setStrokeColor(self.accent); c.setLineWidth(1.8)
        for previous, current in zip(points, points[1:]): c.line(*previous, *current)
        if len(points) == 1:
            c.setFillColor(self.accent); c.circle(*points[0], 2, fill=1, stroke=0)
        c.setFillColor(MUTED)
        if self.buckets:
            c.drawString(left, 10, self.buckets[0].start_at.astimezone(self.zone).strftime('%d/%m/%Y %H:%M'))
            grain = {'hour': 'hora', 'day': 'día', 'week': 'semana', 'month': 'mes'}.get(self.grain, self.grain)
            c.drawCentredString(self.width / 2, 10, f'Agrupación: {grain}')
            c.drawRightString(right, 10, self.buckets[-1].start_at.astimezone(self.zone).strftime('%d/%m/%Y %H:%M'))


def ticket_pdf_table(rows, zone, width, *, light=True, accent=BLUE):
    def values():
        for ticket, customer, circuit, sector, department, kind in rows:
            date = lambda value: value.astimezone(zone).strftime('%d/%m/%Y\n%H:%M') if value else '—'
            yield [ticket.reference, 'Abierto' if ticket.status == 'OPEN' else 'Cerrado', ticket.title,
                   f'{customer.customer_code}\n{customer.name}', circuit.circuit_code,
                   ticket.node.name if ticket.node else "Sin asignar",
                   ticket.responsible.name if ticket.responsible else "Sin asignar", sector.name,
                   kind.name, date(ticket.start_at),
                   f'{date(ticket.end_at)}\n{duration_text(ticket.duration_seconds) if ticket.duration_seconds is not None else ("En curso" if ticket.status == "OPEN" else "Sin fecha de fin")}']
    return modern_table(
        ['Referencia', 'Estado', 'Título', 'Cliente', 'Circuito', 'Nodo', 'Responsable', 'Sector', 'Tipo', 'Inicio', 'Fin / Duración'],
        values(),
        [width * fraction for fraction in [.10, .06, .115, .115, .105, .075, .085, .07, .075, .10, .10]],
        reference=True, light=light, accent=accent,
    )


def duration_text(seconds):
    if seconds is None: return '—'
    seconds = int(seconds)
    if seconds < 60: return f'{seconds} s'
    minutes = seconds // 60
    days, hours = divmod(minutes // 60, 24)
    return ' '.join(part for part in [f'{days} d' if days else '', f'{hours} h' if hours else '', f'{minutes % 60} min' if minutes % 60 else ''] if part)


class BarsGraphic(Flowable):
    """Barras vectoriales; los rankings conservan su tabla completa."""
    def __init__(self, rows, width, value_field='count', limit=10, accent=BLUE):
        super().__init__()
        self.rows = list(rows)[:limit]
        self.width = width
        self.value_field = value_field
        self.accent = accent
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
            canvas.setFillColor(self.accent)
            canvas.rect(label_width, y - 2, (self.width - label_width - 65) * value / maximum, 9, fill=1, stroke=0)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(self.width, y, duration_text(value) if self.value_field == 'average_duration_seconds' else str(value))


class ActivityGraphic(TrendGraphic):
    def __init__(self, *args, labels=('Iniciadas', 'Cerradas'), accent=BLUE, line_colors=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.labels = labels
        self.accent = accent
        self.line_colors = line_colors

    def draw(self):
        canvas = self.canv
        left, right, base, top = 28, self.width - 10, 25, 108
        maximum = max((max(row.started, row.closed) for row in self.buckets), default=0) or 1
        canvas.setFont(FONT, 7)
        for index in range(5):
            y = base + (top - base) * index / 4
            canvas.setStrokeColor(BORDER); canvas.setLineWidth(.4); canvas.line(left, y, right, y)
            canvas.setFillColor(MUTED); canvas.drawRightString(left - 5, y - 2, f'{maximum * index / 4:g}')
        if self.line_colors:
            color_started, color_closed = self.line_colors
        elif self.labels == ('Incrementos', 'Decrementos'):
            color_started = EMERALD
            color_closed = colors.HexColor('#0284c7')
        elif self.labels == ('Bajas', 'Reactivaciones'):
            color_started = colors.HexColor('#475569')
            color_closed = EMERALD
        else:
            color_started = self.accent
            color_closed = EMERALD
        for field, color, label, x in [('started', color_started, self.labels[0], left), ('closed', color_closed, self.labels[1], left + (95 if self.labels == ('Iniciadas', 'Cerradas') else 120))]:
            canvas.setFillColor(color); canvas.drawString(x, 115, label)
            points = [(left + index * (right - left) / max(1, len(self.buckets) - 1), base + getattr(row, field) * (top - base) / maximum) for index, row in enumerate(self.buckets)]
            canvas.setStrokeColor(color); canvas.setLineWidth(1.5)
            for previous, current in zip(points, points[1:]): canvas.line(*previous, *current)
            if len(points) == 1: canvas.circle(*points[0], 2, fill=1, stroke=0)
        if self.buckets:
            canvas.setFillColor(MUTED)
            canvas.drawString(left, 10, self.buckets[0].start_at.astimezone(self.zone).strftime('%d/%m %H:%M'))
            canvas.drawRightString(right, 10, self.buckets[-1].start_at.astimezone(self.zone).strftime('%d/%m %H:%M'))
