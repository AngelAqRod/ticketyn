"""Milestone 1: real sessions/PostgreSQL, read-only audit, no external services."""
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ticketyn.models import Responsible
from ticketyn.models.security import SecurityAudit
from ticketyn.security.service import audit, principal, reset_password, set_access
from ticketyn.security import roles
from test_security_foundation import security_client, make_account, login, authorize
from test_security_authorization import account_role


def ready(security_client, role='SUPERADMIN'):
    client, app, factory = security_client
    id = make_account(factory, role=role)
    authorize(client, login(client))
    return client, app, factory, id


def entries(factory, event):
    with factory() as session:
        return session.scalars(select(SecurityAudit).where(SecurityAudit.event == event)).all()


def test_login_success_failed_groups_and_no_automatic_activity_events(security_client, caplog):
    client, app, factory = security_client
    id = make_account(factory)
    now = [1000.0]; app.state.security.clock = lambda: now[0]
    for _ in range(3):
        assert login(client, 'secret-wrong', 'Nobody').status_code == 401
    groups = entries(factory, 'LOGIN_FAILED_GROUP')
    assert len(groups) == 1 and groups[0].actor_id is None
    assert groups[0].details == {'username': 'Nobody', 'ip': 'testclient', 'operation': 'LOGIN'}
    now[0] += 901
    assert login(client, 'secret-wrong', 'Nobody').status_code == 401
    assert len(entries(factory, 'LOGIN_FAILED_GROUP')) == 2
    response = login(client, username='tEsTeR')
    authorize(client, response)
    token = response.json()['token']
    rows = entries(factory, 'LOGIN_SUCCEEDED')
    assert len(rows) == 1 and rows[0].actor_id == id and rows[0].target_id == id
    assert rows[0].details == {'username': 'Tester', 'ip': 'testclient'}
    for _ in range(3):
        assert client.get('/api/auth/me').status_code == 200
        assert client.get('/api/security/audit').status_code == 200
    assert client.post('/api/auth/activity', json={}).status_code == 200
    assert len(entries(factory, 'LOGIN_SUCCEEDED')) == 1
    with factory() as session:
        persisted = json.dumps([row.details for row in session.scalars(select(SecurityAudit))])
        hashed = session.get(Responsible, id).password_hash
    assert not any(secret in persisted + caplog.text for secret in ('secret-wrong', 'test-only-password', token, hashed, app.state.security.digest(token)))
    assert 'account_key' not in persisted


@pytest.mark.parametrize('failure_point', ['audit', 'commit'])
def test_login_audit_failure_revokes_only_provisional_session(security_client, monkeypatch, caplog, failure_point):
    client, app, factory, _ = ready(security_client)
    existing = client.headers['Authorization'][7:]
    original_commit = None
    if failure_point == 'commit':
        from sqlalchemy.orm import Session
        original_commit = Session.commit
        def failed_commit(session):
            raise SQLAlchemyError('test-private-database-secret')
        monkeypatch.setattr(Session, 'commit', failed_commit)
    else:
        monkeypatch.setattr('ticketyn.api.auth.audit', lambda *a, **k: (_ for _ in ()).throw(SQLAlchemyError('test-private-database-secret')))
    response = login(client)
    assert response.status_code == 503 and 'token' not in response.json()
    if original_commit:
        monkeypatch.setattr('sqlalchemy.orm.Session.commit', original_commit)
    assert len(app.state.security.snapshot()) == 1 and app.state.security.get(existing) is not None
    assert len(entries(factory, 'LOGIN_SUCCEEDED')) == 1
    assert 'test-private-database-secret' not in response.text + caplog.text


def test_failed_group_persistence_error_is_sanitized_and_creates_no_session(security_client, monkeypatch, caplog):
    client, app, factory = security_client
    make_account(factory)
    with patch('ticketyn.api.auth.audit', side_effect=SQLAlchemyError('hidden-secret')):
        response = login(client, 'wrong-sensitive')
    assert response.status_code == 503 and not app.state.security.snapshot()
    assert not entries(factory, 'LOGIN_FAILED_GROUP')
    assert 'wrong-sensitive' not in response.text + caplog.text and 'hidden-secret' not in response.text + caplog.text


def test_session_capacity_does_not_audit_a_success(security_client):
    client, app, factory = security_client
    make_account(factory)
    for _ in range(5):
        assert login(client).status_code == 200
    assert login(client).status_code == 409
    assert len(entries(factory, 'LOGIN_SUCCEEDED')) == 5
    assert len(app.state.security.snapshot()) == 5


@pytest.mark.parametrize('role,expected', [('SUPERADMIN', 200), ('ADMIN', 200), ('OPERATOR', 403), ('AUDITOR', 403), ('CUSTOM', 403)])
def test_audit_permissions_and_single_read_only_endpoint(security_client, role, expected):
    client, app, factory, _ = ready(security_client, role)
    assert client.get('/api/security/audit').status_code == expected
    for method, path in [('POST', '/api/security/audit'), ('PATCH', '/api/security/audit/1'), ('DELETE', '/api/security/audit/1'),
                         ('GET', '/api/security/audit/summary'), ('GET', '/api/security/audit/export/pdf'),
                         ('POST', '/api/security/audit/cleanup')]:
        assert client.request(method, path).status_code == 403
    client.headers.pop('Authorization')
    assert client.get('/api/security/audit').status_code == 401


def test_custom_permission_changes_immediately_and_never_refreshes_session(security_client):
    client, app, factory, id = ready(security_client, 'CUSTOM')
    token = client.headers['Authorization'][7:]
    activity = app.state.security.get(token).last_activity
    assert client.get('/api/security/audit').status_code == 403
    account_role(factory, id, grants=['audit.view'])
    assert client.get('/api/security/audit').status_code == 200
    assert app.state.security.get(token).last_activity == activity
    account_role(factory, id, grants=[])
    assert client.get('/api/security/audit').status_code == 403


def test_role_history_scope_before_count_pagination_and_metadata(security_client):
    client, app, factory, id = ready(security_client)
    with factory() as session:
        session.add_all([SecurityAudit(event=event, source='HTTP', success=True, details={'role_id': 99})
                         for event in ['ROLE_CREATED', 'ROLE_CHANGED', 'ROLE_DELETED', 'ROLE_UNKNOWN_FUTURE']])
        session.commit()
    super_page = client.get('/api/security/audit').json()
    assert any(row['event'] == 'ROLE_CREATED' for row in super_page['items'])
    account_role(factory, id, role='ADMIN')
    page = client.get('/api/security/audit').json()
    assert page['total'] == super_page['total'] - 4
    assert not any(row['event'].startswith('ROLE_') for row in page['items'])
    assert not any(option['code'].startswith('ROLE_') for option in page['events'])
    assert client.get('/api/security/audit?event=ROLE_CHANGED').status_code == 403
    assert client.get('/api/security/audit?event=LEGACY').json()['total'] == 0


def test_combined_filters_dates_unicode_and_order(security_client):
    client, app, factory, id = ready(security_client)
    begin = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    with factory() as session:
        person = session.get(Responsible, id); person.name = 'Ángel NOC'
        for index in range(4):
            session.add(SecurityAudit(actor_id=id, target_id=id, event='PASSWORD_RESET', source='HTTP',
                                      occurred_at=begin + timedelta(hours=index), success=index != 1, details={}))
        session.commit()
    response = client.get('/api/security/audit', params={'event': 'PASSWORD_RESET', 'username': 'ÁNGEL',
        'actor_id': id, 'from_at': '2026-10-20T06:00:00-06:00', 'to_at': '2026-10-20T09:00:00-06:00', 'result': 'SUCCESS'})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page['total'] == 2 and page['limit'] == 50 and page['offset'] == 0
    assert [row['occurred_at'][:19] for row in page['items']] == ['2026-10-20T14:00:00', '2026-10-20T12:00:00']
    assert all(row['actor']['name'] == 'Ángel NOC' for row in page['items'])
    assert client.get('/api/security/audit?username=%25').json()['total'] == 0


def test_pagination_uses_fifty_rows_stable_id_tiebreak_and_empty_page(security_client):
    client, app, factory, _ = ready(security_client)
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with factory() as session:
        rows = [SecurityAudit(event='PASSWORD_RESET', occurred_at=moment, source='HTTP', success=True, details={}) for _ in range(105)]
        session.add_all(rows); session.flush(); ids = [row.id for row in rows]; session.commit()
    pages = [client.get('/api/security/audit', params={'event': 'PASSWORD_RESET', 'offset': offset}).json() for offset in (0, 50, 100, 150)]
    assert [len(page['items']) for page in pages] == [50, 50, 5, 0]
    assert all(page['total'] == 105 for page in pages)
    assert [row['id'] for page in pages for row in page['items']] == sorted(ids, reverse=True)


@pytest.mark.parametrize('query', ['limit=1', 'limit=51', 'offset=-1', 'actor_id=0', 'event=UNKNOWN', 'result=INVALID',
    'from_at=2026-01-01T00:00:00', 'from_at=2026-02-01T00:00:00Z&to_at=2026-01-01T00:00:00Z', 'username=' + 'x' * 101, 'attribute=password_hash'])
def test_invalid_filters_rejected_without_echoing_input(security_client, query):
    client, _, _, _ = ready(security_client)
    response = client.get('/api/security/audit?' + query)
    assert response.status_code == 422, response.text
    assert 'password_hash' not in response.text


def test_legacy_information_is_not_inferred_or_exposed_and_reads_preserve_rows(security_client):
    client, app, factory, id = ready(security_client)
    before = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with factory() as session:
        legacy = SecurityAudit(event='LOGIN_FAILED_GROUP', occurred_at=before, source='HTTP', success=False,
            details={'account_key': 'historical-hash-sentinel', 'password': 'secret-old-password', 'token': 'old-token'})
        unknown = SecurityAudit(event='UNKNOWN-secret-event', occurred_at=before, source='secret-source', success=True,
            details={'password': 'secret-unknown'})
        session.add_all([legacy, unknown]); session.flush(); saved = (legacy.id, unknown.id); session.commit()
    response = client.get('/api/security/audit?event=LOGIN_FAILED_GROUP')
    row = response.json()['items'][0]
    assert row['identifier'] is None and row['actor'] is None and row['target'] is None
    assert row['occurred_at'].startswith('2020-01-01')
    assert row['details'] == [{'label': 'Información del grupo', 'value': 'Registro histórico; cantidad de intentos no disponible.'}]
    unknown_row = client.get('/api/security/audit?event=LEGACY').json()['items'][0]
    assert unknown_row['event'] == 'LEGACY' and unknown_row['source'] == 'Origen histórico' and unknown_row['details'] == []
    assert not any(value in response.text + json.dumps(unknown_row) for value in ('historical-hash-sentinel', 'secret-old-password', 'old-token', 'secret-unknown', 'secret-event', 'secret-source'))
    with factory() as session:
        legacy = session.get(SecurityAudit, saved[0])
        assert legacy.details['account_key'] == 'historical-hash-sentinel' and legacy.occurred_at == before
        assert session.get(SecurityAudit, saved[1]).event == 'UNKNOWN-secret-event'


def test_metadata_whitelist_including_nested_snapshots(security_client):
    _, _, factory, _ = ready(security_client)
    with factory() as session:
        audit(session, 'ROLE_CHANGED', details={'role_id': 1, 'token': 'hidden',
            'before': {'name': 'Ingeniería', 'description': 'old-private-description', 'permissions': ['tickets.view', 'secret-invalid-permission'], 'password_hash': 'secret-hash'},
            'after': {'name': 'NOC', 'description': 'new-private-description', 'permissions': ['tickets.view', 'tickets.edit'], 'token': 'secret-token'}})
        audit(session, 'LOGIN_FAILED_GROUP', details={'username': 'missing', 'account_key': 'secret-account-hash', 'token': 'secret-token', 'password': 'secret-password'})
        session.commit()
    details = entries(factory, 'ROLE_CHANGED')[0].details
    assert details['before'] == {'name': 'Ingeniería', 'permissions': ['tickets.view']}
    assert details['after'] == {'name': 'NOC', 'permissions': ['tickets.edit', 'tickets.view']}
    assert details['description_changed'] is True
    raw = json.dumps([details, entries(factory, 'LOGIN_FAILED_GROUP')[0].details])
    assert 'secret' not in raw and 'private-description' not in raw and 'token' not in raw and 'hash' not in raw


def test_malformed_legacy_metadata_cannot_be_inferred_through_filters(security_client):
    client, _, factory, _ = ready(security_client)
    with factory() as session:
        session.add_all([
            SecurityAudit(event='LOGIN_FAILED_GROUP', source='HTTP', success=False,
                          details={'username': {'token': 'hidden-dictionary-secret'}}),
            SecurityAudit(event='LOGIN_FAILED_GROUP', source='HTTP', success=False,
                          details={'username': 'x' * 100 + 'hidden-after-limit'}),
        ])
        session.commit()
    for value in ('hidden-dictionary-secret', 'hidden-after-limit'):
        result = client.get('/api/security/audit', params={'username': value})
        assert result.status_code == 200 and result.json()['total'] == 0
    assert 'hidden-dictionary-secret' not in client.get('/api/security/audit').text


def test_existing_critical_events_actor_and_rollback_remain_correct(security_client):
    client, app, factory, id = ready(security_client)
    with factory() as session:
        actor = principal(session, id)
        custom = roles.create_role(session, actor, 'Seguridad de prueba')
        session.commit(); role_id = custom.id
        roles.update_role(session, actor, role_id, {'permissions': ['tickets.view']}); session.commit()
        person = Responsible(name='Otra persona', username='noc', password_hash=session.get(Responsible, id).password_hash,
                             security_role_id=role_id, access_granted=True)
        session.add(person); session.flush(); person_id = person.id; session.commit()
        reset_password(session, person_id, 'temporary-private', actor_id=id); session.commit()
        set_access(session, person_id, False, actor_id=id); session.commit()
        set_access(session, person_id, True, actor_id=id); session.commit()
    second = login(client).json()['token']
    assert client.post('/api/auth/sessions/close-others').status_code == 200
    assert app.state.security.get(second) is None
    event_rows = client.get('/api/security/audit').json()['items']
    assert {'ROLE_CREATED', 'ROLE_CHANGED', 'PASSWORD_RESET', 'ACCESS_DISABLED', 'ACCESS_ENABLED', 'SESSION_CLOSED'} <= {row['event'] for row in event_rows}
    reset = next(row for row in event_rows if row['event'] == 'PASSWORD_RESET')
    assert reset['actor']['id'] == id and reset['target']['id'] == person_id
    with patch('ticketyn.security.service.audit', side_effect=SQLAlchemyError('not-persisted')):
        with factory() as session:
            with pytest.raises(SQLAlchemyError): set_access(session, person_id, False, actor_id=id)
            session.rollback()
    with factory() as session:
        assert session.get(Responsible, person_id).access_granted
        assert session.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.event == 'ACCESS_DISABLED')) == 1
