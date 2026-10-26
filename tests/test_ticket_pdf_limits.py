"""Bulk PDF admission and volume checks, using only the ephemeral PostgreSQL fixture."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from unittest.mock import Mock

from fastapi import HTTPException
import pytest

from ticketyn.api import ticket_pdf_limits as limits
from ticketyn.api import ticket_exports
from ticketyn.schemas.ticket_export import TicketExportFilters
from test_internal_tickets import payload as internal_payload


def test_admission_is_atomic_and_released_after_error():
    limiter = limits.TicketPdfLimiter(clock=lambda: 100)
    started, finish = Event(), Event()

    def render():
        with limiter.reserve(1):
            started.set()
            assert finish.wait(5)
            raise ValueError('render failed')

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(render)
        try:
            assert started.wait(5)
            with pytest.raises(HTTPException) as error:
                with limiter.reserve(2):
                    pytest.fail('second render admitted')
            assert error.value.status_code == 429
            assert int(error.value.headers['Retry-After']) > 0
        finally:
            finish.set()
        with pytest.raises(ValueError, match='render failed'):
            future.result()
    with limiter.reserve(2):
        pass


def test_frequency_uses_user_identity_and_expiring_counters():
    now = [100.0]
    limiter = limits.TicketPdfLimiter(clock=lambda: now[0])
    with limiter.reserve(1):
        pass
    now[0] += 0.2
    with pytest.raises(HTTPException) as error:
        with limiter.reserve(1):
            pytest.fail('repeat admitted')
    assert error.value.headers['Retry-After'] == '30'
    with limiter.reserve(2):
        pass
    now[0] += 30
    with limiter.reserve(1):
        assert set(limiter.next_allowed) == {1}


@pytest.mark.parametrize('internal', [False, True])
@pytest.mark.parametrize('statistical', [False, True])
def test_volume_limits_reject_complete_set_before_rendering(
        api_client, ticket_payload, monkeypatch, internal, statistical):
    base = '/api/internal-tickets' if internal else '/api/tickets'
    body = internal_payload(api_client) if internal else ticket_payload
    for title in ('first', 'last'):
        result = api_client.post(base, json={**body, 'title': title, 'start_at': '2020-01-01T12:00:00Z'})
        assert result.status_code == 201, result.text
    path = ('/api/reports/internal-tickets' if internal else '/api/reports') if statistical else base
    now = [100.0]
    api_client.app.state.ticket_pdf_limiter.clock = lambda: now[0]
    monkeypatch.setattr(limits, 'MAX_TICKETS', 1)
    # The renderer must never see an oversized result, regardless of pagination.
    build = Mock(side_effect=AssertionError('rendered excessive PDF'))
    target = 'reports.export_pdf' if statistical else 'internal_ticket_exports.build_pdf' if internal else 'ticket_exports.build_pdf'
    monkeypatch.setattr(f'ticketyn.api.{target}', build)
    rejected = api_client.get(path + '/export/pdf', params={'limit': 1, 'offset': 1} if not statistical else {})
    assert rejected.status_code == 413, rejected.text
    build.assert_not_called()
    now[0] += 30
    monkeypatch.setattr(limits, 'MAX_TICKETS', 2000)
    monkeypatch.setattr(limits, 'MAX_TEXT_CHARACTERS', 1)
    rejected = api_client.get(path + '/export/pdf')
    assert rejected.status_code == 413 and 'extenso' in rejected.json()['detail']
    build.assert_not_called()
    assert not api_client.app.state.ticket_pdf_limiter.busy
    assert api_client.get(base).status_code == 200
    assert api_client.get(path + '/export/xlsx').status_code == 200


@pytest.mark.parametrize('internal', [False, True])
def test_pdf_boundaries_filtering_no_truncation_and_individual_compatibility(
        api_client, ticket_payload, monkeypatch, internal):
    base = '/api/internal-tickets' if internal else '/api/tickets'
    body = internal_payload(api_client) if internal else ticket_payload
    created = api_client.post(base, json={**body, 'title': 'selected'}).json()
    api_client.post(base, json={**body, 'title': 'excluded'})
    monkeypatch.setattr(limits, 'MAX_TICKETS', 1)
    response = api_client.get(base + '/export/pdf', params={'search': 'selected', 'limit': 1, 'offset': 99})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b'%PDF-')
    assert api_client.get(base + '/export/pdf').status_code == 429
    assert api_client.get(f'{base}/{created["id"]}/reports/internal/pdf').status_code == 200


def test_all_bulk_routes_share_frequency_and_other_sessions_cannot_bypass(api_client):
    routes = ['/api/tickets', '/api/internal-tickets', '/api/reports', '/api/reports/internal-tickets']
    assert api_client.get(routes[0] + '/export/pdf').status_code == 200
    user_id = api_client.app.state.test_security_account_id
    session = api_client.app.state.security.snapshot()[0]
    token = api_client.app.state.security.create(user_id, session.revision)
    for route in routes:
        response = api_client.get(route + '/export/pdf', headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 429
        assert 1 <= int(response.headers['Retry-After']) <= 30


def test_text_limit_boundary_is_inclusive():
    session = Mock()
    filters = TicketExportFilters()
    extra = sum(len(str(v)) for v in filters.model_dump().values() if v is not None)
    session.execute.return_value.one.return_value = (limits.MAX_TICKETS, limits.MAX_TEXT_CHARACTERS - extra)
    limits.validate_pdf_volume(session, filters)
    session.execute.return_value.one.return_value = (limits.MAX_TICKETS, limits.MAX_TEXT_CHARACTERS - extra + 1)
    with pytest.raises(HTTPException) as error:
        limits.validate_pdf_volume(session, filters)
    assert error.value.status_code == 413


@pytest.mark.parametrize('field', ['description', 'circuit_description'])
def test_narrative_text_is_measured_before_loading_or_rendering(
        api_client, ticket_payload, monkeypatch, field):
    body = dict(ticket_payload)
    if field == 'description':
        body['description'] = 'ñ' * 1500
    else:
        response = api_client.patch(f'/api/circuits/{body["circuit_id"]}', json={'description': 'ñ' * 1500})
        assert response.status_code == 200
    assert api_client.post('/api/tickets', json=body).status_code == 201
    monkeypatch.setattr(limits, 'MAX_TEXT_CHARACTERS', 1000)
    monkeypatch.setattr(ticket_exports, 'fonts', Mock(side_effect=AssertionError('rendering started')))
    response = api_client.get('/api/tickets/export/pdf')
    assert response.status_code == 413 and 'extenso' in response.json()['detail']


def test_render_error_closes_output_and_releases_admission(api_client, monkeypatch):
    output = BytesIO()
    monkeypatch.setattr('tempfile.SpooledTemporaryFile', lambda **kwargs: output)
    def fail(*args, **kwargs):
        raise ValueError('render failed')
    monkeypatch.setattr(ticket_exports, 'build_pdf', fail)
    with pytest.raises(ValueError, match='render failed'):
        api_client.get('/api/tickets/export/pdf')
    assert output.closed
    assert not api_client.app.state.ticket_pdf_limiter.busy
