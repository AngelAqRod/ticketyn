from pathlib import Path

import pytest
from test_fms import operation_payload, create
from test_ticket_exports import pdf_strings
from test_fms_reports import RANGE

BASE = '/api/fms/reports/'
KINDS = ['activations', 'capacity-changes', 'circuit-lifecycle']


def add(client, kind, payload):
    extra = {'operation_type': 'INCREASE', 'new_capacity': '2000', 'new_unit': 'Mbps'} if kind == 'capacity-changes' else {'operation_type': 'REACTIVATE'} if kind == 'circuit-lifecycle' else {}
    return create(client, '/api/' + kind, {**payload, **extra})


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('scope', [None, 'sector_id', 'node_id', 'responsible_id'])
def test_statistics_pdf_same_filters_and_historical_data(api_client, operation_payload, kind, scope, pdf_strings):
    row = add(api_client, kind, operation_payload)
    # Out of period and created with the same administrative timestamp.
    add(api_client, kind, {**operation_payload, 'effective_at': RANGE['to']})
    node = create(api_client, '/api/nodes', {'name': 'NO USAR NODO ACTUAL'})
    sector = create(api_client, '/api/sectors', {'name': 'NO USAR SECTOR ACTUAL'})
    api_client.patch(f"/api/circuits/{row['circuit_id']}", json={'node_id': node['id'], 'sector_id': sector['id']})
    filters = {**RANGE, **({scope: row[scope]} if scope else {})}
    summary = api_client.get(BASE + kind + '/summary', params=filters).json()
    response = api_client.get(BASE + kind + '/export/pdf', params=filters)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b'%PDF') and b'%%EOF' in response.content
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert 'ticketyn-analisis-' + kind in response.headers['content-disposition']
    content = ' '.join(pdf_strings)
    assert 'GESTIÓN DE SERVICIOS · OPERACIONES FMS' in content
    assert 'GESTIÓN DE INCIDENCIAS' not in content
    assert 'America/Guatemala' in content and 'fin exclusivo' in content
    assert 'Detalle de operaciones · 1 registros' in content
    assert 'NO USAR NODO ACTUAL' not in content and 'NO USAR SECTOR ACTUAL' not in content
    assert 'Nodo de prueba' in content and 'Sector de prueba' in content
    assert 'Página 1 /' in content
    assert sum(x['count'] for x in summary['trend']) == 1
    if scope:
        assert {'sector_id': 'Por Sector', 'node_id': 'Por Nodo', 'responsible_id': 'Por Responsable'}[scope] in content
        assert 'Top 10 de clientes' not in content
    elif kind == 'activations': assert 'Top 10 de clientes' in content
    if kind == 'capacity-changes':
        assert '2 Gbps' in content
        assert '1 operaciones sin capacidad anterior conocida' in content
        assert 'Incrementos' in content and 'Decrementos' in content
    elif kind == 'circuit-lifecycle': assert 'Bajas' in content and 'Reactivaciones' in content
    else: assert content.count(row['reference']) == 1


@pytest.mark.parametrize('kind', KINDS)
def test_empty_pdf_and_parameters(api_client, kind, pdf_strings):
    response = api_client.get(BASE + kind + '/export/pdf')
    assert response.status_code == 200
    Path(f'/tmp/ticketyn-statistical-empty-{kind}.pdf').write_bytes(response.content)
    content = ' '.join(pdf_strings)
    assert 'Todos · Sin restricción temporal' in content
    assert 'Sin operaciones en el período.' in content
    assert 'Sin resultados.' in content
    for query in [{'from': RANGE['from']}, {'timezone': 'Invalid'}, {'granularity': 'hour'}, {'sector_id': -1}, {'from': RANGE['to'], 'to': RANGE['from']}]:
        assert api_client.get(BASE + kind + '/export/pdf', params=query).status_code == 422
    assert api_client.get(BASE + kind + '/export/pdf', params={'node_id': 999999}).status_code == 404
    assert api_client.get(BASE + 'invalid/export/pdf').status_code == 422


def test_all_pages_and_long_text_with_actual_charts(api_client, operation_payload, db_session, pdf_strings):
    from ticketyn.models.fms import CapacityChange
    from datetime import datetime, timezone
    records = [CapacityChange(**{k: v for k, v in operation_payload.items() if k != 'effective_at'}, effective_at=datetime(2020,1,1,tzinfo=timezone.utc), sector_id=None, node_id=None, operation_type='INCREASE', new_capacity='2000', new_unit='Mbps', description=f'RECORD-{i:03} & <especial> ' + ('Texto extenso áéíóú.\n' * 150 if i == 25 else 'Detalle.')) for i in range(65)]
    db_session.add_all(records); db_session.commit()
    response = api_client.get(BASE + 'capacity-changes/export/pdf', params={'limit': 1, 'offset': 50})
    assert response.status_code == 200, response.text
    content = ' '.join(pdf_strings)
    for i in range(65): assert content.count(f'RECORD-{i:03}') == 1
    assert content.index('RECORD-064') < content.index('RECORD-000')
    assert any('Página 2 /' in x for x in pdf_strings)
    assert content.count('Código del circuito') > 1  # Repeated table headers.
    assert '2 Gbps' in content and 'Sinregistrar' in ''.join(content.split())
    assert all(row.new_capacity == 2000 for row in records)  # Presentation does not mutate stored values.
    Path('/tmp/ticketyn-fms-statistical-capacity.pdf').write_bytes(response.content)


def test_graphics_receive_summary_buckets_and_all_reasons(api_client, operation_payload, monkeypatch, pdf_strings):
    import ticketyn.api.fms_report_exports as exports
    captured = []
    original = exports.ActivityGraphic
    def graphic(rows, *args, **kwargs):
        captured.append([(row.started, row.closed) for row in rows])
        return original(rows, *args, **kwargs)
    monkeypatch.setattr(exports, 'ActivityGraphic', graphic)
    reason = create(api_client, '/api/deactivation-reasons', {'name': 'Motivo preservado'})
    create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': 'DEACTIVATE', 'reason_id': reason['id']})
    add(api_client, 'circuit-lifecycle', operation_payload)
    api_client.patch(f"/api/deactivation-reasons/{reason['id']}", json={'active': False})
    response = api_client.get(BASE + 'circuit-lifecycle/export/pdf', params=RANGE)
    assert response.status_code == 200
    assert captured == [[(1, 1)]]
    assert 'Motivo preservado' in ' '.join(pdf_strings)
    Path('/tmp/ticketyn-fms-statistical-lifecycle.pdf').write_bytes(response.content)


def test_limits_fail_explicitly_and_generation_errors_are_controlled(api_client, operation_payload, monkeypatch):
    import ticketyn.api.fms_report_exports as exports
    add(api_client, 'activations', operation_payload)
    monkeypatch.setattr(exports, 'MAX_OPERATIONS', 0)
    response = api_client.get(BASE + 'activations/export/pdf')
    assert response.status_code == 413 and 'Reduce el período' in response.json()['detail']
    monkeypatch.setattr(exports, 'MAX_OPERATIONS', 2000)
    monkeypatch.setattr(exports, 'MAX_TEXT_CHARACTERS', 1)
    assert api_client.get(BASE + 'activations/export/pdf').status_code == 413
    monkeypatch.setattr(exports, 'MAX_TEXT_CHARACTERS', 2_000_000)
    def fail(*args, **kwargs): raise RuntimeError('PRIVATE DATABASE_URL')
    monkeypatch.setattr(exports, 'build_pdf', fail)
    response = api_client.get(BASE + 'activations/export/pdf')
    assert response.status_code == 500 and 'PRIVATE' not in response.text


def test_selected_element_excludes_other_operations(api_client, operation_payload, pdf_strings):
    selected = add(api_client, 'activations', operation_payload)
    sector = create(api_client, '/api/sectors', {'name': 'SECTOR AJENO'})
    person = create(api_client, '/api/responsibles', {'name': 'RESPONSABLE AJENO'})
    node = create(api_client, '/api/nodes', {'name': 'NODO AJENO'})
    api_client.patch(f"/api/circuits/{operation_payload['circuit_id']}", json={'node_id': node['id'], 'sector_id': sector['id']})
    other = add(api_client, 'activations', {**operation_payload, 'responsible_id': person['id']})
    for field in ['sector_id', 'node_id', 'responsible_id']:
        pdf_strings.clear()
        response = api_client.get(BASE + 'activations/export/pdf', params={**RANGE, field: selected[field]})
        assert response.status_code == 200
        content = ' '.join(pdf_strings)
        assert selected['reference'] in content
        for value in [other['reference'], 'SECTOR AJENO', 'NODO AJENO', 'RESPONSABLE AJENO']: assert value not in content
        assert 'Detalle de operaciones · 1 registros' in content
    Path('/tmp/ticketyn-fms-statistical-activation.pdf').write_bytes(response.content)


def test_spooled_files_are_closed_on_success_and_failure(api_client, operation_payload, monkeypatch):
    import ticketyn.api.fms_report_exports as exports
    original = exports.SpooledTemporaryFile
    outputs = []
    def spool(*args, **kwargs):
        output = original(*args, **kwargs); outputs.append(output); return output
    monkeypatch.setattr(exports, 'SpooledTemporaryFile', spool)
    add(api_client, 'activations', operation_payload)
    assert api_client.get(BASE + 'activations/export/pdf').status_code == 200
    assert outputs[-1].closed
    monkeypatch.setattr(exports, 'MAX_OPERATIONS', 0)
    assert api_client.get(BASE + 'activations/export/pdf').status_code == 413
    assert outputs[-1].closed


def test_many_reasons_use_legible_graphics_without_omissions(api_client, operation_payload, monkeypatch, pdf_strings):
    import ticketyn.api.fms_report_exports as exports
    original = exports.BarsGraphic
    sizes = []
    def graphic(rows, *args, **kwargs):
        sizes.append(len(rows)); return original(rows, *args, **kwargs)
    monkeypatch.setattr(exports, 'BarsGraphic', graphic)
    for i in range(11):
        reason = create(api_client, '/api/deactivation-reasons', {'name': f'Motivo gráfico {i:02}'})
        create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': 'DEACTIVATE', 'reason_id': reason['id']})
    response = api_client.get(BASE + 'circuit-lifecycle/export/pdf', params=RANGE)
    assert response.status_code == 200
    assert sizes == [10, 1]
    content = ' '.join(pdf_strings)
    for i in range(11): assert f'Motivo gráfico {i:02}' in content
    assert '11–11 de 11' in content


def test_known_decimal_variations_and_negative_net_match_summary(api_client, operation_payload, pdf_strings):
    for kind, old, old_unit, new, new_unit in [('INCREASE', '500', 'Mbps', '1.5', 'Gbps'), ('DECREASE', '2', 'Gbps', '500', 'Mbps'), ('INCREASE', None, None, '1', 'Gbps')]:
        create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': kind, 'previous_capacity': old, 'previous_unit': old_unit, 'new_capacity': new, 'new_unit': new_unit})
    before = api_client.get('/api/capacity-changes').json()
    summary = api_client.get(BASE + 'capacity-changes/summary', params=RANGE).json()
    from decimal import Decimal
    assert Decimal(summary['kpis']['known_added_mbps']) == 1000
    assert Decimal(summary['kpis']['known_reduced_mbps']) == 1500
    assert Decimal(summary['kpis']['known_net_mbps']) == -500
    response = api_client.get(BASE + 'capacity-changes/export/pdf', params=RANGE)
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    for value in ['1 Gbps', '1.5 Gbps', '−500 Mbps', '1 operaciones sin capacidad anterior conocida', 'Detalle de operaciones · 3 registros']: assert value in content
    assert api_client.get('/api/capacity-changes').json() == before
