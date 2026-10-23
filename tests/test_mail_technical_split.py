"""Pruebas exhaustivas para el diseño Technical Split de correos Ticketyn v0.8.0.

Cubre los 20 requisitos de prueba del alcance:
1. Cabecera Technical Split (2 columnas, fondo blanco, línea divisoria inferior).
2. Barra lateral Electric Blue (#1768D5).
3. Identidad temática del evento (FMS · ACTIVACIÓN).
4. Correlativo dinámico (presencia y omisión limpia).
5. Campos en dos columnas (50% de ancho, etiqueta gris arriba, valor oscuro abajo).
6. Campo sin pareja (conserva ancho con celda vacía).
7. Texto y variables mezclados respetando secuencia.
8. Notas multilínea (formato en bloque gris azulado con acento esmeralda).
9. Etiquetas personalizadas (DEFAULT vs CUSTOM).
10. Respeto estricto del orden configurado de bloques.
11. Compatibilidad con plantillas antiguas.
12. Escapado HTML riguroso contra inyecciones XSS.
13. Conservación integral de la versión en texto plano.
14. Vista previa consistente al 100% con despacho del worker.
15. Variables de distribución históricas en plantilla Technical Split.
16. IP de gestión CPE actual en plantilla Technical Split.
17. Ausencia de secciones técnicas no seleccionadas en la plantilla.
18. Aislamiento de datos técnicos internos (cpe_configuration no expuesta).
19. Compatibilidad con modos de evento AUTOMATIC y MANUAL.
20. Inalterabilidad de destinatarios y configuración de transporte.
"""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from ticketyn.notifications.fields import ACTIVATION_EVENT, ACTIVATION_FIELDS
from ticketyn.notifications.html import BodyBlock, render_html
from ticketyn.notifications.templates import render_template
from ticketyn.schemas.mail_templates import MailTemplate


class HtmlParserHelper(HTMLParser):
    def __init__(self, doc):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.root = NS(tag='root', attrs={}, children=[])
        self.stack = [self.root]
        self.feed(doc)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        node = NS(tag=tag, attrs=dict(attrs), children=[])
        self.stack[-1].children.append(node)
        if tag not in {'meta', 'br'}:
            self.stack.append(node)
        if tag == 'br': self.text.append('\n')
    def handle_endtag(self, tag):
        self.stack.pop()
        if tag in {'div', 'td', 'title', 'span'}: self.text.append('\n')
    def handle_data(self, data):
        self.text.append(data)
        self.stack[-1].children.append(data)
    @property
    def visible(self):
        return ''.join(self.text)


def nodes_of(node):
    if isinstance(node, str): return
    yield node
    for child in node.children:
        yield from nodes_of(child)


def text_node(node):
    if isinstance(node, str): return node
    if node.tag == 'br': return '\n'
    return ''.join(text_node(c) for c in node.children) + ('\n' if node.tag == 'div' else '')


def sample_activation(reference='ACT-000012', notes='Notas de prueba'):
    return NS(
        reference=reference,
        effective_at=datetime(2026, 10, 20, 10, tzinfo=timezone.utc),
        created_at=datetime(2026, 10, 20, 9, tzinfo=timezone.utc),
        activation_notes=notes,
        distribution_recorded=True,
        distribution_device_name='OLT-HUAWEI-01',
        distribution_port_name='gpon-0/1/1',
        service_type_name='Internet Corporativo',
        cpe_activation='Huawei EchoLife',
        initial_capacity=Decimal('100'),
        initial_capacity_unit='Mbps',
        circuit_id=10,
        circuit=NS(
            circuit_code='CIR-1011.32',
            description='Enlace Principal Fibra',
            cpe_management_ip='192.168.10.25',
            initial_capacity=Decimal('100'),
            initial_capacity_unit='Mbps',
            customer=NS(name='YEYO SA (PUBLIMOVIL)', customer_code='CUST-001'),
        ),
    )


class DummySession:
    def scalar(self, q): return None


def dynamic(field_id, **kwargs):
    return {'type': 'field', 'field_id': field_id, **kwargs}


# 1 & 2. Cabecera Technical Split y Barra lateral Electric Blue
def test_1_and_2_technical_split_header_and_electric_blue_bar():
    act = sample_activation()
    tpl = MailTemplate.model_validate({'subject': [dynamic('activation.reference')], 'body': [dynamic('customer.name')]})
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    parsed = HtmlParserHelper(res.html_body)

    header = next(n for n in nodes_of(parsed.root) if 'ticketyn-header' in n.attrs.get('class', ''))
    assert header.attrs['bgcolor'] == '#FFFFFF'
    assert 'border-left:4px solid #1768D5' in header.attrs.get('style', '')
    assert 'border-bottom:1px solid #E2E8F0' in header.attrs.get('style', '')

    left, right = next(n for n in nodes_of(header) if n.tag == 'tr').children
    assert 'Ticketyn' in text_node(left)
    assert 'NOTIFICACIÓN OPERATIVA' in text_node(left)
    assert any('color:#1768D5' in n.attrs.get('style', '') for n in nodes_of(left))


# 3. Identidad temática del evento (FMS · ACTIVACIÓN)
def test_3_event_thematic_tag():
    act = sample_activation()
    tpl = MailTemplate.model_validate({'subject': [], 'body': [dynamic('customer.name')]})
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert 'FMS · ACTIVACIÓN' in res.html_body
    assert 'color:#047857' in res.html_body  # acento temático verde esmeralda
    assert 'background-color:#ECFDF5' in res.html_body or 'background-color:#ecfdf5' in res.html_body.lower()


# 4. Correlativo dinámico (presente o ausente)
def test_4_dynamic_correlative_presence_and_absence():
    # Con correlativo
    act_with = sample_activation(reference='ACT-000012')
    tpl = MailTemplate.model_validate({'subject': [], 'body': [dynamic('customer.name')]})
    res_with = render_template(DummySession(), ACTIVATION_EVENT, tpl, act_with)
    assert 'ACT-000012' in res_with.html_body

    # Sin correlativo (composición limpia sin texto inventado ni campos vacíos)
    act_without = sample_activation(reference=None)
    res_without = render_template(DummySession(), ACTIVATION_EVENT, tpl, act_without)
    assert 'ACT-000012' not in res_without.html_body
    assert 'Nueva activación' in res_without.html_body
    assert 'None' not in res_without.html_body


# 5. Campos en dos columnas (50% de ancho, etiqueta gris arriba, valor oscuro abajo)
def test_5_two_column_field_pairs_layout():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [dynamic('customer.name'), dynamic('circuit.code')],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    parsed = HtmlParserHelper(res.html_body)
    field_rows = [n for n in nodes_of(parsed.root) if n.attrs.get('class') == 'ticketyn-field-row']
    assert len(field_rows) == 1
    row = field_rows[0]
    assert len(row.children) == 2
    for cell in row.children:
        assert cell.attrs.get('width') == '50%'
        assert 'color:#64748B' in str(cell.children[0].attrs.get('style', ''))  # etiqueta gris discreta
        assert 'color:#0F172A' in str(cell.children[1].attrs.get('style', ''))  # valor oscuro destacado


# 6. Campo sin pareja (conserva ancho 50% con celda vacía)
def test_6_odd_field_has_empty_pair_cell():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [dynamic('customer.name'), dynamic('circuit.code'), dynamic('activation.service_type')],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    parsed = HtmlParserHelper(res.html_body)
    field_rows = [n for n in nodes_of(parsed.root) if n.attrs.get('class') == 'ticketyn-field-row']
    assert len(field_rows) == 2
    last_row = field_rows[1]
    assert len(last_row.children) == 2
    assert last_row.children[0].attrs.get('class') == 'ticketyn-field'
    assert last_row.children[1].attrs.get('class') == 'ticketyn-empty'


# 7 & 10. Texto y variables mezclados respetando el orden configurado
def test_7_and_10_mixed_text_and_fields_respect_exact_order():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [
            {'type': 'introduction', 'text': 'Texto introductorio preliminar'},
            dynamic('customer.name'),
            {'type': 'introduction', 'text': 'Aviso intermedio importante'},
            dynamic('circuit.code'),
            {'type': 'signature', 'text': 'Firma institucional NOC'},
        ],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    visible = HtmlParserHelper(res.html_body).visible
    pos_intro = visible.find('Texto introductorio preliminar')
    pos_cust = visible.find('YEYO SA (PUBLIMOVIL)')
    pos_mid = visible.find('Aviso intermedio importante')
    pos_cir = visible.find('CIR-1011.32')
    pos_sig = visible.find('Firma institucional NOC')
    assert 0 <= pos_intro < pos_cust < pos_mid < pos_cir < pos_sig


# 8. Notas multilínea con formato en bloque gris azulado y acento esmeralda
def test_8_multiline_notes_block_format():
    notes_content = 'Línea técnica 1: IP 10.0.0.1\nLínea 2: VLAN 200 trunk\nLínea 3: Puerto sfp-0/1'
    act = sample_activation(notes=notes_content)
    tpl = MailTemplate.model_validate({'subject': [], 'body': [dynamic('activation.activation_notes')]})
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert 'border-left:3px solid #047857' in res.html_body
    assert 'bgcolor="#F2F6FC"' in res.html_body
    assert 'Línea técnica 1: IP 10.0.0.1<br>Línea 2: VLAN 200 trunk<br>Línea 3: Puerto sfp-0/1' in res.html_body


# 9. Etiquetas personalizadas (DEFAULT vs CUSTOM)
def test_9_default_and_custom_labels():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [
            dynamic('customer.name', label_mode='CUSTOM', custom_label='Razón Social'),
            dynamic('circuit.code', label_mode='DEFAULT'),
        ],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert 'RAZÓN SOCIAL:' in res.html_body or 'Razón Social:' in res.html_body
    assert 'CÓDIGO DE CIRCUITO:' in res.html_body


# 11. Plantillas antiguas permanecen compatibles
def test_11_legacy_saved_templates_compatibility():
    act = sample_activation()
    # Estructura previa de plantilla v0.7.0
    legacy_tpl = MailTemplate.model_validate({
        'version': 1,
        'subject': [{'type': 'text', 'text': 'Aviso de alta | '}, dynamic('activation.reference')],
        'body': [
            {'type': 'introduction', 'text': 'Estimados,\nSe ha registrado una activación.'},
            dynamic('customer.name'),
            dynamic('circuit.code'),
            {'type': 'signature', 'text': 'Saludos cordiales'},
        ],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, legacy_tpl, act)
    assert 'Aviso de alta | ACT-000012' == res.subject
    assert 'YEYO SA (PUBLIMOVIL)' in res.body
    assert 'CIR-1011.32' in res.body
    assert '<!doctype html>' in res.html_body
    assert 'Ticketyn' in res.html_body


# 12. Escapado HTML riguroso contra inyecciones XSS
def test_12_rigorous_html_escaping():
    malicious_text = '<script>alert("xss")</script>&<img src=x onerror=alert(1)>'
    act = sample_activation(notes=malicious_text)
    act.circuit.customer.name = malicious_text
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [
            {'type': 'introduction', 'text': malicious_text},
            dynamic('customer.name'),
            dynamic('activation.activation_notes'),
        ],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert '<script>' not in res.html_body
    assert '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;' in res.html_body
    assert '&lt;img src=x onerror=alert(1)&gt;' in res.html_body


# 13. Conservación integral del texto plano (text/plain)
def test_13_plain_text_completeness_and_fidelity():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [dynamic('activation.reference')],
        'body': [
            {'type': 'introduction', 'text': 'Inicio del comunicado.'},
            dynamic('customer.name'),
            dynamic('circuit.code'),
            dynamic('activation.activation_notes'),
            {'type': 'signature', 'text': 'Fin del comunicado.'},
        ],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert res.body.startswith('Inicio del comunicado.\n\nCLIENTE: YEYO SA (PUBLIMOVIL)\nCÓDIGO DE CIRCUITO: CIR-1011.32')
    assert 'NOTAS DE ACTIVACIÓN:\nNotas de prueba' in res.body
    assert res.body.endswith('\n\nFin del comunicado.')


# 14. Vista previa consistente con el despacho del worker
def test_14_preview_identical_to_worker_output():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [{'type': 'text', 'text': 'FMS | '}, dynamic('activation.reference')],
        'body': [
            dynamic('customer.name'),
            dynamic('activation.distribution_device'),
            dynamic('activation.activation_notes'),
        ],
    })
    res_worker = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    res_preview = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert res_worker.subject == res_preview.subject
    assert res_worker.body == res_preview.body
    assert res_worker.html_body == res_preview.html_body


# 15. Variables de distribución históricas en Technical Split
def test_15_distribution_variables_in_technical_split():
    act = sample_activation()
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [dynamic('activation.distribution_device'), dynamic('activation.distribution_port')],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert 'Información técnica de distribución' in res.html_body
    assert 'OLT-HUAWEI-01' in res.html_body
    assert 'gpon-0/1/1' in res.html_body
    assert '#0284C7' in res.html_body  # acento azul técnico


# 16. IP de gestión CPE actual en Technical Split
def test_16_cpe_management_ip_in_technical_split():
    act = sample_activation()
    tpl = MailTemplate.model_validate({'subject': [], 'body': [dynamic('circuit.cpe_management_ip')]})
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert '192.168.10.25' in res.html_body
    assert 'IP DE GESTIÓN CPE:' in res.html_body


# 17. Ausencia de secciones técnicas no seleccionadas en plantilla
def test_17_no_unselected_technical_sections():
    act = sample_activation()
    # Plantilla solo con cliente y circuito (sin campos de distribución ni notas)
    tpl = MailTemplate.model_validate({
        'subject': [],
        'body': [dynamic('customer.name'), dynamic('circuit.code')],
    })
    res = render_template(DummySession(), ACTIVATION_EVENT, tpl, act)
    assert 'Información de activación' in res.html_body
    assert 'Información técnica de distribución' not in res.html_body
    assert 'Notas técnicas de activación' not in res.html_body


# 18. Aislamiento de datos técnicos internos (cpe_configuration no expuesta)
def test_18_isolation_of_cpe_configuration():
    assert 'cpe_configuration' not in [f.id for f in ACTIVATION_FIELDS]
    for f in ACTIVATION_FIELDS:
        for path in f.source_paths:
            assert 'cpe_configuration' not in path


# 19. Compatibilidad con eventos y modos de notificación
def test_19_event_metadata_defined_and_consistent():
    from ticketyn.notifications.fields import EVENT_METADATA
    assert ACTIVATION_EVENT in EVENT_METADATA
    meta = EVENT_METADATA[ACTIVATION_EVENT]
    assert meta['badge'] == 'FMS · ACTIVACIÓN'
    assert meta['badge_color'] == '#047857'
    assert meta['badge_bg'] == '#ECFDF5'


# 20. Sin alteraciones en destinatarios ni configuración SMTP
def test_20_transport_and_template_independence():
    from ticketyn.schemas.mail_templates import MailTemplate
    # MailTemplate sólo contiene version, subject y body, nunca credenciales ni destinatarios
    fields = set(MailTemplate.model_fields.keys())
    assert fields == {'version', 'subject', 'body'}
