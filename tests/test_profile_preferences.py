"""Personal preferences never grant access to operational or security identity."""
import pytest
from sqlalchemy import select, text, create_engine
from uuid import uuid4
from ticketyn.models import Responsible
from test_security_foundation import security_client, make_account, login, authorize  # noqa: F401
from test_e2e_update_migration import cli


def test_preferences_persist_without_privilege_or_session_changes(security_client):
    client, app, factory = security_client
    id = make_account(factory, role='CUSTOM')
    authorize(client, login(client))
    token = client.headers['Authorization'][7:]
    activity = app.state.security.get(token).last_activity
    profile = client.get('/api/auth/profile').json()
    assert profile['id'] == id and profile['preferences'] == {'home_page': 'DASHBOARD'}
    with factory() as session:
        before = session.get(Responsible, id)
        identity = (before.name, before.username, before.security_role_id, before.position_id, before.password_hash, before.access_revision)
    result = client.patch('/api/auth/profile/preferences', json={'home_page': 'DASHBOARD'})
    assert result.status_code == 200 and result.json() == {'home_page': 'DASHBOARD'}
    with factory() as session:
        person = session.get(Responsible, id)
        assert person.preferred_home_page == 'DASHBOARD'
        assert (person.name, person.username, person.security_role_id, person.position_id, person.password_hash, person.access_revision) == identity
    assert client.get('/api/auth/profile').json()['preferences'] == result.json()
    assert app.state.security.get(token).last_activity == activity
    for secret in (token, identity[4], 'password_hash', 'session_token'):
        assert secret not in client.get('/api/auth/profile').text


@pytest.mark.parametrize('field,value', [('role_id', 1), ('security_role_id', 1), ('position_id', 1),
    ('permissions', ['roles.manage']), ('active', False), ('access_granted', True), ('id', 7), ('name', 'Otra identidad'), ('email', 'noc@example.net')])
def test_own_profile_rejects_account_and_operational_edits(security_client, field, value):
    client, app, factory = security_client
    make_account(factory, role='CUSTOM'); authorize(client, login(client))
    assert client.patch('/api/auth/profile/preferences', json={'home_page': 'DASHBOARD', field: value}).status_code == 422
    assert client.patch('/api/auth/profile', json={field: value}).status_code == 403


@pytest.mark.parametrize('value', ['/missing', 'PROD', None, 1])
def test_unavailable_start_page_never_creates_a_destination(security_client, value):
    client, app, factory = security_client
    make_account(factory); authorize(client, login(client))
    assert client.patch('/api/auth/profile/preferences', json={'home_page': value}).status_code == 422
    assert client.get('/api/auth/profile').json()['preferences']['home_page'] == 'DASHBOARD'


def test_preferences_allow_my_tickets_and_persist(security_client):
    client, app, factory = security_client
    id = make_account(factory); authorize(client, login(client))
    result = client.patch('/api/auth/profile/preferences', json={'home_page': 'MY_TICKETS'})
    assert result.status_code == 200 and result.json() == {'home_page': 'MY_TICKETS'}
    with factory() as session:
        person = session.get(Responsible, id)
        assert person.preferred_home_page == 'MY_TICKETS'
    assert client.get('/api/auth/profile').json()['preferences'] == {'home_page': 'MY_TICKETS'}
    auth_data = client.get('/api/auth/me').json()
    assert auth_data.get('preferred_home_page') == 'MY_TICKETS'


def test_preferences_require_authentication_and_do_not_target_another_person(security_client):
    client, app, factory = security_client
    assert client.patch('/api/auth/profile/preferences', json={'home_page': 'DASHBOARD'}).status_code == 401
    make_account(factory); authorize(client, login(client))
    with factory() as session:
        other = Responsible(name='Otro responsable', preferred_home_page='MY_TICKETS')
        session.add(other); session.flush(); other_id = other.id; session.commit()
    assert client.patch(f'/api/auth/profile/preferences?responsible_id={other_id}', json={'home_page': 'DASHBOARD'}).status_code == 200
    with factory() as session:
        assert session.get(Responsible, other_id).preferred_home_page == 'MY_TICKETS'


def test_profile_preference_migration_roundtrip_preserves_identity(postgres_engine):
    name = 'profile_migration_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0040_escalation_recommend_ack')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO responsibles(name,username,password_hash,active,operational_selectable) VALUES ('Histórico','hist','fixture-hash-preserved',true,false)"))
            original = connection.scalar(text('SELECT to_jsonb(r) FROM responsibles r'))
        cli(engine.url, 'upgrade', '0041_profile_preferences')
        with engine.connect() as connection:
            after = connection.scalar(text('SELECT to_jsonb(r) FROM responsibles r'))
            assert after.pop('preferred_home_page') == 'DASHBOARD'
            assert after == original
        cli(engine.url, 'downgrade', '0040_escalation_recommend_ack')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT to_jsonb(r) FROM responsibles r')) == original
        cli(engine.url, 'upgrade', '0041_profile_preferences')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))
