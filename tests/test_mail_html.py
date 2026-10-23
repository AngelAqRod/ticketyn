"""Offline HTML, unchanged text, and preview/MIME/worker equivalence."""
from datetime import datetime, timezone
from decimal import Decimal
from email.parser import BytesParser
from email.policy import default
from html.parser import HTMLParser
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_activation_notifications import (activation_env, activation_client, no_external_mail,
                                         create_activation, operation_snapshot)  # noqa: F401
from test_ticket_concurrency import concurrent_database  # noqa: F401
from ticketyn.models.fms import ActivationIntervention
from ticketyn.models.mail_jobs import MailNotificationRequest as Job
from ticketyn.models.mail_notifications import MailEventConfig
from ticketyn.notifications import processor
from ticketyn.notifications.fields import ACTIVATION_EVENT, ACTIVATION_FIELDS
from ticketyn.notifications.smtp import SendResult, build_message
from ticketyn.notifications.templates import render_template
from ticketyn.schemas.mail_templates import MailTemplate


class Html(HTMLParser):
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []
        self.root = NS(tag='root', attrs={}, children=[])
        self.stack = [self.root]
        self.feed(document)
        assert len(self.stack) == 1
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        node = NS(tag=tag, attrs=dict(attrs), children=[])
        self.stack[-1].children.append(node)
        if tag not in {'meta', 'br'}:
            self.stack.append(node)
        if tag == 'br': self.text.append('\n')
    def handle_endtag(self, tag):
        assert self.stack[-1].tag == tag
        self.stack.pop()
        if tag in {'div', 'td', 'h1', 'title'}: self.text.append('\n')
    def handle_data(self, data):
        self.text.append(data)
        self.stack[-1].children.append(data)
    @property
    def visible(self):
        return ''.join(self.text)


def nodes(node):
    if isinstance(node, str):
        return
    yield node
    for child in node.children:
        yield from nodes(child)


def text_of(node):
    if isinstance(node, str):
        return node
    if node.tag == 'br':
        return '\n'
    return ''.join(text_of(child) for child in node.children) + ('\n' if node.tag == 'div' else '')


def field_rows(parsed):
    return [node for node in nodes(parsed.root) if node.attrs.get('class') == 'ticketyn-field-row']


def sequence(parsed):
    """Field pairs and full-width notes, in their actual HTML reading order."""
    result = []
    for node in nodes(parsed.root):
        if node.attrs.get('class') == 'ticketyn-field-row':
            result.append(('fields', tuple(text_of(cell) for cell in node.children
                                           if cell.attrs.get('class') == 'ticketyn-field')))
        elif node.tag == 'table' and node.attrs.get('bgcolor') == '#F2F6FC':
            result.append(('notes', text_of(node)))
    return result


class NoExtraQueries:
    def scalar(self, query):
        return None  # No effective capacity change: use the existing fallback.


def example(notes='Primera línea\n\n  Puerto MiXto ñ'):
    return NS(reference='ACT-000001', effective_at=datetime(2026, 10, 16, 5, tzinfo=timezone.utc),
              created_at=datetime(2026, 10, 19, 12, tzinfo=timezone.utc), activation_notes=notes,
              sector=NS(name='Sector histórico'), node=None, responsible=NS(name='Operador ñ'),
              service_type_name='Servicio Histórico', cpe_activation='CPE Original',
              initial_capacity=Decimal('100'), initial_capacity_unit='Mbps', circuit_id=1,
              circuit=NS(circuit_code='CIR-1', description='Descripción MiXta', sector=NS(name='Sector actual'),
                         node=NS(name='Nodo actual'), service_type=NS(name='Servicio actual'),
                         cpe_model=NS(name='CPE actual'), initial_capacity=Decimal('200'), initial_capacity_unit='Mbps',
                         customer=NS(name='Cliente Ñandú', customer_code='CL-1')))


def render(blocks, activation=None):
    template = MailTemplate.model_validate({'subject': [{'type': 'text', 'text': 'Asunto MiXto |'},
        {'type': 'field', 'field_id': 'activation.reference'}], 'body': blocks})
    return render_template(NoExtraQueries(), ACTIVATION_EVENT, template, activation or example())


def field(identifier, **kwargs):
    return {'type': 'field', 'field_id': identifier, **kwargs}


def assert_passive(document):
    parsed = Html(document)
    allowed = {'html', 'head', 'meta', 'style', 'title', 'body', 'table', 'tr', 'td', 'div', 'h1', 'br'}
    assert {tag for tag, _ in parsed.tags} <= allowed
    for _, attrs in parsed.tags:
        assert not any(key.startswith('on') or key in {'src', 'href', 'action', 'srcdoc'} for key in attrs)
        assert 'url(' not in attrs.get('style', '').lower()
    for node in nodes(parsed.root):
        if node.tag == 'style':
            assert 'url(' not in text_of(node) and '@import' not in text_of(node)
    assert "default-src 'none'" in document and "base-uri 'none'" in document
    return parsed


def test_html_wordmark_layout_and_plain_text_without_images():
    result = render([{'type': 'introduction', 'text': 'Estimados,\nRegistro técnico.'},
                     field('customer.name'), field('activation.activation_notes'),
                     {'type': 'signature', 'text': 'Saludos,\nNoc ágil'}])
    assert result.subject == 'Asunto MiXto | ACT-000001'
    assert result.body == ('Estimados,\nRegistro técnico.\n\nCLIENTE: Cliente Ñandú\n'
                           'NOTAS DE ACTIVACIÓN:\nPrimera línea\n\n  Puerto MiXto ñ\n\nSaludos,\nNoc ágil')
    parsed = assert_passive(result.html_body)
    assert 'Ticketyn' in parsed.visible and 'Registro de activación' in parsed.visible
    assert 'Estimados,\nRegistro técnico.' in parsed.visible
    assert 'Primera línea\n\n  Puerto MiXto ñ' in parsed.visible
    assert 'Saludos,\nNoc ágil' in parsed.visible
    assert 'bgcolor="#1769D5"' not in result.html_body and 'bgcolor="#F2F6FC"' in result.html_body
    assert 'max-width:640px' in result.html_body and 'table-layout:fixed' in result.html_body
    assert all(tag != 'img' for tag, _ in parsed.tags)  # No image dependency, CID or external logo.


def test_minimal_header_title_footer_and_mobile_fallback():
    parsed = assert_passive(render([field('customer.name')]).html_body)
    header = next(node for node in nodes(parsed.root) if 'ticketyn-header' in node.attrs.get('class', ''))
    assert header.attrs['bgcolor'] == '#FFFFFF'
    assert 'border-left:4px solid #1768D5' in header.attrs.get('style', '')
    assert 'border-bottom:1px solid #E2E8F0' in header.attrs.get('style', '')
    left, right = next(node for node in nodes(header) if node.tag == 'tr').children
    assert left.attrs['align'] == 'left'
    assert 'Ticketyn' in text_of(left)
    assert 'NOTIFICACIÓN OPERATIVA' in text_of(left)
    assert any('color:#1768D5' in n.attrs.get('style', '') for n in nodes(left))
    assert right.attrs['align'] == 'right'
    assert 'FMS · ACTIVACIÓN' in text_of(right)
    assert 'Nueva activación' in text_of(right)
    assert 'ACT-000001' in text_of(right)
    footer = next(node for node in nodes(parsed.root) if node.attrs.get('bgcolor') == '#F8FAFC')
    assert footer.attrs['align'] == 'center' and 'Ticketyn · Gestión operativa' in text_of(footer)
    document = render([field('customer.name')]).html_body
    assert '@media screen and (max-width:480px)' in document
    assert '.ticketyn-blocks,.ticketyn-blocks>tbody,.ticketyn-blocks>tbody>tr,.ticketyn-blocks>tbody>tr>td{display:block!important;width:100%!important;box-sizing:border-box;}' in document
    assert '.ticketyn-blocks>tbody>tr>.ticketyn-empty{display:none!important;}' in document
    blocks_table = next(node for node in nodes(parsed.root) if node.attrs.get('class') == 'ticketyn-blocks')
    assert blocks_table.tag == 'table' and blocks_table.attrs['width'] == '100%'
    assert 'display:grid' not in document


@pytest.mark.parametrize('count', [0, 1, 2, 3, 4, 5])
def test_normal_fields_fill_two_equal_columns_in_configured_order(count):
    identifiers = ['circuit.description', 'activation.reference', 'customer.name', 'circuit.node', 'activation.initial_capacity'][:count]
    result = render([field(identifier, label_mode='CUSTOM', custom_label=f'Etiqueta MiXta {index}') for index, identifier in enumerate(identifiers)])
    parsed = assert_passive(result.html_body)
    rows = field_rows(parsed)
    assert len(rows) == (count + 1) // 2
    seen = []
    for index, row in enumerate(rows):
        assert len(row.children) == 2
        assert all(cell.tag == 'td' and cell.attrs['width'] == '50%' for cell in row.children)
        assert all('border' not in cell.attrs['style'] for cell in row.children)
        cells = [cell for cell in row.children if cell.attrs['class'] == 'ticketyn-field']
        assert len(cells) == min(2, count - 2 * index)
        seen.extend(text_of(cell).split(':', 1)[0] for cell in cells)
    assert seen == [f'Etiqueta MiXta {index}' for index in range(count)]
    if count % 2:
        assert rows[-1].children[1].attrs['class'] == 'ticketyn-empty'
        assert text_of(rows[-1].children[1]) == ''


@pytest.mark.parametrize('order,expected', [
    (['n', 'a', 'b'], ['n', ('a', 'b')]),
    (['a', 'b', 'n', 'c', 'd'], [('a', 'b'), 'n', ('c', 'd')]),
    (['a', 'n', 'b', 'c', 'd'], [('a',), 'n', ('b', 'c'), ('d',)]),
    (['a', 'b', 'c', 'n'], [('a', 'b'), ('c',), 'n']),
    (['n', 'n', 'a', 'n', 'b'], ['n', 'n', ('a',), 'n', ('b',)]),
])
def test_full_width_notes_interrupt_pairs_without_reordering(order, expected):
    identifiers = {'a': 'customer.name', 'b': 'circuit.code', 'c': 'circuit.node', 'd': 'activation.initial_capacity', 'n': 'activation.activation_notes'}
    result = render([field(identifiers[key], label_mode='CUSTOM', custom_label=key) for key in order])
    parsed = assert_passive(result.html_body)
    actual = [tuple(value.split(':', 1)[0] for value in values) if kind == 'fields' else 'n'
              for kind, values in sequence(parsed)]
    assert actual == expected
    for node in nodes(parsed.root):
        if node.tag == 'table' and node.attrs.get('bgcolor') == '#F2F6FC':
            assert 'border-left:3px solid #047857' in node.attrs['style']
            assert 'n:\nPrimera línea\n\n  Puerto MiXto ñ' in text_of(node)
    assert sum(node.attrs.get('colspan') == '2' and 'ticketyn-section-header' not in node.attrs.get('class', '') for node in nodes(parsed.root)) == order.count('n')


@pytest.mark.parametrize('kind,text', [('introduction', 'Introducción intermedia\nLiteral'),
                                    ('signature', 'Firma intermedia\nLiteral'), ('introduction', '\n\n')])
def test_configured_text_and_spacing_also_interrupt_field_pairs(kind, text):
    result = render([field('customer.name'), {'type': kind, 'text': text}, field('circuit.code')])
    parsed = assert_passive(result.html_body)
    assert [len(values) for kind, values in sequence(parsed) if kind == 'fields'] == [1, 1]
    ordered = list(nodes(parsed.root))
    text_cell = next(node for node in ordered if node.attrs.get('colspan') == '2' and text_of(node) == text)
    first, second = field_rows(parsed)
    assert ordered.index(first) < ordered.index(text_cell) < ordered.index(second)


def test_absent_fields_do_not_reserve_cells_or_move_notes():
    result = render([field('activation.node'), field('customer.name'), field('circuit.code')], example(None))
    parsed = assert_passive(result.html_body)
    rows = field_rows(parsed)
    assert len(rows) == 1 and len(rows[0].children) == 2
    assert 'Cliente Ñandú' in text_of(rows[0].children[0]) and 'CIR-1' in text_of(rows[0].children[1])
    assert 'NODO' not in parsed.visible and '#F2F6FC' not in result.html_body


def test_long_unbroken_value_keeps_equal_column_width_and_literal_data():
    activation = example()
    activation.circuit.description = 'Ñ<&' * 3000
    result = render([field('circuit.description'), field('customer.name')], activation)
    row = field_rows(assert_passive(result.html_body))[0]
    assert all(cell.attrs['width'] == '50%' for cell in row.children)
    assert 'overflow-wrap:anywhere' in result.html_body and 'word-wrap:break-word' in result.html_body
    assert activation.circuit.description in text_of(row.children[0])
    assert activation.circuit.description in result.body


@pytest.mark.parametrize('custom', [False, True])
def test_all_fields_order_labels_unicode_and_historical_values(custom):
    blocks = [field(item.id, **({'label_mode': 'CUSTOM', 'custom_label': f'Mi etiqueta {index} ñ'} if custom else {}))
              for index, item in enumerate(reversed(ACTIVATION_FIELDS))]
    # A signature in the middle must not be moved to the end by presentation.
    blocks.insert(3, {'type': 'signature', 'text': 'Firma Intermedia ñ'})
    result = render(blocks)
    visible = assert_passive(result.html_body).visible
    cursor = 0
    for block in blocks:
        if block['type'] == 'signature': marker = block['text']
        else:
            if block['field_id'] == 'activation.node': continue  # Historical missing value, no current fallback.
            entry = next(item for item in ACTIVATION_FIELDS if item.id == block['field_id'])
            marker = (block['custom_label'] if custom else entry.label.upper()) + ':'
        index = visible.find(marker, cursor)
        assert index >= cursor, marker
        cursor = index + len(marker)
    for value in ('Cliente Ñandú', 'Descripción MiXta', 'Servicio Histórico', 'Servicio actual',
                  'Sector histórico', 'Sector actual', 'CPE Original', 'CPE actual', '100 Mbps', '200 Mbps'):
        assert value in visible and value in result.body
    assert 'FECHA EFECTIVA DE ACTIVACIÓN' in visible if not custom else 'Mi etiqueta' in visible


@pytest.mark.parametrize('notes', ['Una línea', 'Línea uno\n\n  Línea tres', 'Primero\r\nSegundo', None, '', '   '])
def test_notes_selected_multiline_custom_label_and_empty_values(notes):
    result = render([field('activation.activation_notes', label_mode='CUSTOM', custom_label='Detalles MiXtos ñ')], example(notes))
    visible = assert_passive(result.html_body).visible
    if notes and notes.strip():
        assert result.body == 'Detalles MiXtos ñ:\n' + notes
        assert 'Detalles MiXtos ñ:\n' + notes.replace('\r\n', '\n') in visible
        assert 'bgcolor="#F2F6FC"' in result.html_body
    else:
        assert result.body == 'Detalles MiXtos ñ:\nSin notas registradas'
        assert 'Detalles MiXtos ñ:\nSin notas registradas' in visible
        assert 'bgcolor="#F2F6FC"' in result.html_body


def test_unselected_notes_empty_blocks_and_explicit_newlines():
    result = render([{'type': 'introduction', 'text': ''}, field('activation.reference'),
                     {'type': 'introduction', 'text': '\n\n'}, field('customer.name'),
                     {'type': 'signature', 'text': '  '}])
    assert result.body == 'CORRELATIVO: ACT-000001\n\nCLIENTE: Cliente Ñandú'
    assert '<br><br>' in result.html_body
    assert 'NOTAS DE ACTIVACIÓN' not in result.html_body and '#F2F6FC' not in result.html_body
    assert 'null' not in result.body and 'None' not in result.body


def test_both_formats_reuse_the_same_resolved_values_and_capacity_query():
    calls = []
    class CapacitySession:
        def scalar(self, query):
            calls.append(query)
            return NS(new_capacity=Decimal('300'), new_unit='Mbps')
    template = MailTemplate.model_validate({'subject': [field('circuit.current_capacity')],
                                           'body': [field('circuit.current_capacity'), field('circuit.current_capacity')]})
    result = render_template(CapacitySession(), ACTIVATION_EVENT, template, example())
    assert len(calls) == 1
    assert result.subject == '300 Mbps'
    assert result.body.count('300 Mbps') == 2 and Html(result.html_body).visible.count('300 Mbps') == 2


@pytest.mark.parametrize('source', ['introduction', 'signature', 'label', 'field', 'notes'])
@pytest.mark.parametrize('payload', ['<script>alert("x")</script>', '</td></tr><img src="https://evil.example/x" onerror="alert(1)">',
                                    '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
                                    '<a href="javascript:alert(1)">Ñandú & MiXto</a>', '&lt;img src=x&gt;'])
def test_every_untrusted_text_source_is_escaped(source, payload):
    activation = example(payload if source == 'notes' else None)
    if source == 'field': activation.circuit.customer.name = payload
    block = ({'type': source, 'text': payload} if source in {'introduction', 'signature'} else
             field('activation.activation_notes') if source == 'notes' else
             field('customer.name', **({'label_mode': 'CUSTOM', 'custom_label': payload} if source == 'label' else {})))
    result = render([block], activation)
    parsed = assert_passive(result.html_body)
    assert payload in parsed.visible  # Visible as literal text, never markup.
    assert payload in result.body
    assert result.subject == 'Asunto MiXto | ACT-000001'


def test_mime_alternatives_headers_and_envelope_are_unchanged():
    content = render([field('customer.name'), field('activation.activation_notes')])
    message, sender, recipients = build_message(sender_email='noc@example.com', sender_name='Noc MiXto ñ',
        to=['to@example.com'], cc=['cc@example.com'], bcc=['hidden@example.com', 'to@example.com'], **content.model_dump())
    wire = BytesParser(policy=default).parsebytes(message.as_bytes())
    assert wire.get_content_type() == 'multipart/alternative'
    assert [part.get_content_type() for part in wire.iter_parts()] == ['text/plain', 'text/html']
    assert all(part.get_content_charset() == 'utf-8' for part in wire.iter_parts())
    assert list(wire.iter_attachments()) == []
    assert sender == 'noc@example.com' and recipients == ['to@example.com', 'cc@example.com', 'hidden@example.com']
    assert wire['Bcc'] is None and 'hidden@example.com' not in wire.as_string()
    assert str(wire['Subject']) == content.subject
    for subtype, expected in [('plain', content.body), ('html', content.html_body)]:
        assert wire.get_body(preferencelist=(subtype,)).get_content().replace('\r\n', '\n').removesuffix('\n') == expected


def test_long_notes_are_not_truncated_and_survive_mime_encoding():
    notes = ('Información técnica & <texto literal> ñ\n  Puerto MiXto\n' * 200)[:10000]
    content = render([field('activation.activation_notes')], example(notes))
    assert content.body == 'NOTAS DE ACTIVACIÓN:\n' + notes
    assert notes in Html(content.html_body).visible
    message, _, _ = build_message(sender_email='noc@example.com', sender_name='Ticketyn',
                                 to=['to@example.com'], **content.model_dump())
    parsed = BytesParser(policy=default).parsebytes(message.as_bytes())
    for subtype, expected in [('plain', content.body), ('html', content.html_body)]:
        assert parsed.get_body(preferencelist=(subtype,)).get_content().replace('\r\n', '\n').removesuffix('\n') == expected


@pytest.mark.parametrize('mode', ['AUTOMATIC', 'MANUAL'])
def test_real_preview_and_existing_request_worker_share_both_alternatives(activation_env, activation_client, monkeypatch, mode):
    engine, payload = activation_env
    template = {'version': 1, 'subject': [{'type': 'text', 'text': 'Aviso MiXto |'}, field('activation.reference')],
                'body': [{'type': 'introduction', 'text': 'Estimados,\n\nDatos de activación'},
                         field('customer.name'), field('activation.activation_notes', label_mode='CUSTOM', custom_label='Notas MiXtas ñ'),
                         {'type': 'signature', 'text': 'Saludos,\nNoc MiXto'}]}
    with Session(engine) as session:
        event = session.get(MailEventConfig, ACTIVATION_EVENT)
        event.mode = mode; event.template = template
        event.cc_recipients = ['cc@example.com']; event.bcc_recipients = ['hidden@example.com']
        session.commit()
    activation = create_activation(activation_client, payload)
    if mode == 'MANUAL':
        assert activation_client.post(f"/api/activations/{activation['id']}/notification", json={'revision': 0}).status_code == 202
    with Session(engine) as session:
        before = operation_snapshot(session, activation['id'])
        job_id = session.scalars(select(Job)).one().id
    preview = activation_client.post('/api/mail-notifications/events/' + ACTIVATION_EVENT + '/preview',
                                    json={'activation_id': activation['id'], 'template': template})
    assert preview.status_code == 200, preview.text
    result = preview.json()
    sent = []
    def send(settings, credentials, message, sender, recipients):
        sent.append((message, recipients))
        return SendResult('ACCEPTED')
    monkeypatch.setattr(processor, 'send_message', send)
    assert processor.NotificationProcessor(engine).run_once()
    assert not processor.NotificationProcessor(engine).run_once()
    message, recipients = sent[0]
    assert len(sent) == 1 and str(message['Subject']) == result['subject']
    assert message.get_body(preferencelist=('html',)).get_content().removesuffix('\n') == result['html_body']
    assert message.get_body(preferencelist=('plain',)).get_content().removesuffix('\n') == result['body']
    assert recipients == ['noc@example.com', 'cc@example.com', 'hidden@example.com'] and message['Bcc'] is None
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        assert job.id == job_id and job.state == 'ACCEPTED'
        assert session.get(MailEventConfig, ACTIVATION_EVENT).template == template
        assert operation_snapshot(session, activation['id']) == before
        assert session.scalar(select(func.count()).select_from(ActivationIntervention)) == 0
    assert activation_client.get(f"/api/activations/{activation['id']}").json() == activation
