"""Phase 3, disposable PostgreSQL and real opaque sessions; no operational DB."""
from unittest.mock import patch
import pytest
from sqlalchemy import select, func, text, create_engine
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole, SecurityAudit
from ticketyn.security.service import seed_foundation
from test_security_foundation import security_client, make_account, login, authorize
from test_security_authorization import account_role


def new_person(factory, name='Persona operativa', **values):
    with factory() as s:
        item = Responsible(name=name, **values); s.add(item); s.flush(); id = item.id; s.commit(); return id


def role_id(factory, code='OPERATOR'):
    with factory() as s:
        return s.scalar(select(SecurityRole.id).where(SecurityRole.code == code))


def setup(security_client):
    client, app, factory = security_client
    admin = make_account(factory); authorize(client, login(client))
    person = new_person(factory)
    return client, app, factory, admin, person


def configure(client, id, role, **extra):
    return client.post(f'/api/responsibles/{id}/access', json={'username': 'operator', 'role_id': role, 'access_granted': True, **extra})


def test_same_identity_safe_access_and_temporary_password(security_client, caplog):
    c, app, f, admin, id = setup(security_client)
    with f() as s: before = s.scalar(select(func.count()).select_from(Responsible))
    assert c.get(f'/api/responsibles/{id}/access').json()['account_exists'] is False
    r = configure(c, id, role_id(f), password=' literal á ')
    assert r.status_code == 201, r.text
    assert r.json()['id'] == id and r.json()['temporary_password'] == ' literal á '
    assert r.json()['password_change_required'] is True
    assert configure(c, id, role_id(f)).status_code == 409
    detail = c.get(f'/api/responsibles/{id}/access').json()
    assert detail['effective_access'] and detail['username'] == 'operator'
    assert not {'password_hash', 'password', 'temporary_password'} & detail.keys()
    assert 'username' not in c.get(f'/api/responsibles/{id}').json()
    with f() as s:
        assert s.scalar(select(func.count()).select_from(Responsible)) == before
        assert s.get(Responsible, id).password_hash.startswith('$argon2id$')
        assert ' literal á ' not in str(s.scalars(select(SecurityAudit.details)).all())
    assert ' literal á ' not in caplog.text
    assert login(c, ' literal á ', 'operator').json()['responsible_id'] == id


def test_access_suspension_operational_status_and_availability_independent(security_client):
    c, app, f, admin, id = setup(security_client)
    assert configure(c, id, role_id(f), password='x').status_code == 201
    token = login(c, 'x', 'operator').json()['token']
    assert c.patch(f'/api/responsibles/{id}', json={'operational_selectable': False}).status_code == 200
    assert c.get('/api/auth/me', headers={'Authorization': 'Bearer '+token}).status_code == 200
    assert c.patch(f'/api/responsibles/{id}', json={'active': False}).status_code == 200
    assert c.get('/api/auth/me', headers={'Authorization': 'Bearer '+token}).status_code == 401
    assert c.get(f'/api/responsibles/{id}/access').json()['access_granted']
    assert c.patch(f'/api/responsibles/{id}/access', json={'access_granted': True}).status_code == 422
    assert c.patch(f'/api/responsibles/{id}/access', json={'access_granted': False}).status_code == 200
    assert c.patch(f'/api/responsibles/{id}', json={'active': True}).status_code == 200
    assert login(c, 'x', 'operator').status_code == 401
    assert c.patch(f'/api/responsibles/{id}/access', json={'access_granted': True}).status_code == 200
    assert login(c, 'x', 'operator').status_code == 200
    with f() as s: assert not s.get(Responsible, id).operational_selectable


@pytest.mark.parametrize('values', [{'password_hash':'injected'}, {'active':False}, {'role_id':None}, {'username':'\ninvalid'}, {'access_granted':None}])
def test_access_rejects_extra_fields_and_nulls(security_client, values):
    c, app, f, admin, id = setup(security_client)
    configure(c, id, role_id(f))
    assert c.patch(f'/api/responsibles/{id}/access', json=values).status_code == 422


@pytest.mark.parametrize('password', ['', 'ü'*2049])
def test_access_password_validation_scrubs_errors(security_client, password):
    c, app, f, admin, id = setup(security_client)
    response = configure(c, id, role_id(f), password=password)
    assert response.status_code == 422
    assert 'ü' not in response.text


def test_reset_generated_password_revisions_and_immediate_role(security_client):
    c, app, f, admin, id = setup(security_client)
    configure(c, id, role_id(f), password='x')
    token = login(c, 'x', 'operator').json()['token']
    audit_role = role_id(f, 'AUDITOR')
    assert c.patch(f'/api/responsibles/{id}/access', json={'role_id': audit_role}).status_code == 200
    me = c.get('/api/auth/me', headers={'Authorization': 'Bearer '+token}).json()
    assert me['role'] == 'AUDITOR'
    reset = c.post(f'/api/responsibles/{id}/access/password', json={})
    assert reset.status_code == 200
    assert len(reset.json()['temporary_password']) >= 24
    assert c.get('/api/auth/me', headers={'Authorization': 'Bearer '+token}).status_code == 401
    assert login(c, reset.json()['temporary_password'], 'operator').json()['password_change_required']


def test_access_audit_failure_rolls_back(security_client):
    c, app, f, admin, id = setup(security_client)
    with patch('ticketyn.security.accounts.audit', side_effect=RuntimeError('controlled')):
        with pytest.raises(RuntimeError): configure(c, id, role_id(f), password='x')
    with f() as s:
        p = s.get(Responsible,id)
        assert p.username is None and p.password_hash is None and p.security_role_id is None


def test_admin_scopes_and_last_superadmin(security_client):
    c, app, f, admin, id = setup(security_client)
    assert c.patch(f'/api/responsibles/{admin}/access', json={'access_granted':False}).status_code == 409
    assert c.patch(f'/api/responsibles/{admin}/access', json={'role_id':role_id(f)}).status_code == 409
    configure(c, id, role_id(f, 'ADMIN'), password='x')
    with f() as s: s.get(Responsible,id).password_change_required=False; s.commit()
    authorize(c, login(c, 'x', 'operator'))
    assert c.get(f'/api/responsibles/{admin}/access').status_code == 403
    assert c.patch(f'/api/responsibles/{id}/access', json={'role_id':role_id(f,'SUPERADMIN')}).status_code == 403
    assert admin not in [row['id'] for row in c.get('/api/responsibles/access').json()]
    another = new_person(f, 'Otra persona')
    assert c.post(f'/api/responsibles/{another}/access', json={'username':'another','role_id':role_id(f,'SUPERADMIN')}).status_code == 403
    assert c.post(f'/api/responsibles/{another}/access', json={'username':'another','role_id':role_id(f)}).status_code == 201


def test_profile_and_own_sessions_no_grants_no_activity_or_token_leaks(security_client):
    c, app, f = security_client
    id = make_account(f, role='CUSTOM')
    tokens = [login(c).json()['token'] for _ in range(3)]
    c.headers['Authorization'] = 'Bearer '+tokens[0]
    last = app.state.security.get(tokens[0]).last_activity
    profile = c.get('/api/auth/profile').json()
    assert profile['id'] == id and profile['role_name']
    assert profile['department'] is None and profile['position'] is None
    from ticketyn.models import Department, Position
    with f() as s:
        dept = Department(name='NOC')
        s.add(dept); s.flush()
        pos = Position(name='N2', department_id=dept.id)
        s.add(pos); s.flush()
        person = s.get(Responsible, id)
        person.department_id = dept.id; person.position_id = pos.id
        s.commit()
    with_dept = c.get('/api/auth/profile').json()
    assert with_dept['department']['name'] == 'NOC' and with_dept['position']['name'] == 'N2'
    result = c.get('/api/auth/sessions')
    rows = result.json(); assert len(rows)==3 and sum(r['current'] for r in rows)==1
    assert all(token not in result.text for token in tokens)
    assert all(app.state.security.digest(token) not in result.text for token in tokens)
    assert app.state.security.get(tokens[0]).last_activity == last
    assert c.post('/api/auth/sessions/close-others', json={}).json()['closed'] == 2
    assert len(c.get('/api/auth/sessions').json()) == 1
    assert c.get('/api/security/sessions').status_code == 403


def test_admin_session_scope_and_audit_before_revocation(security_client):
    c, app, f, admin, id = setup(security_client)
    configure(c,id,role_id(f),password='x')
    with f() as s: s.get(Responsible,id).password_change_required=False; s.commit()
    token = login(c,'x','operator').json()['token']
    rows = c.get('/api/security/sessions').json()
    target = next(row for row in rows if row['responsible_id']==id)
    assert c.get('/api/auth/sessions', headers={'Authorization':'Bearer '+token}).json()[0]['id']==target['id']
    own = next(row for row in rows if row['current'])
    assert c.post(f"/api/auth/sessions/{own['id']}/revoke", json={}, headers={'Authorization':'Bearer '+token}).status_code==404
    with patch('ticketyn.api.security_accounts.audit',side_effect=RuntimeError('controlled')):
        with pytest.raises(RuntimeError): c.post(f"/api/security/sessions/{target['id']}/revoke",json={})
    assert app.state.security.get(token) is not None
    assert c.post(f"/api/security/sessions/{target['id']}/revoke",json={}).status_code==200
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+token}).status_code==401
    with f() as s: assert s.scalar(select(SecurityAudit.id).where(SecurityAudit.event=='SESSION_TERMINATED_ADMIN'))


def test_session_admin_permission_independent_of_access_administration(security_client):
    c, app, f, admin, id = setup(security_client)
    configure(c,id,role_id(f,'AUDITOR'),password='x')
    with f() as s: s.get(Responsible,id).password_change_required=False; s.commit()
    target_token=login(c,'x','operator').json()['token']
    account_role(f,admin,grants=['sessions.manage','tickets.view'])
    rows=c.get('/api/security/sessions').json()
    # Auditor has broader capabilities, so it is outside this custom manager's scope.
    assert rows==[]
    assert c.get('/api/responsibles/access').status_code==403
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+target_token}).status_code==200


def test_historical_availability_lists_and_limited_permissions(security_client):
    c, app, f, admin, id=setup(security_client)
    other=new_person(f,'Sin login seleccionable')
    assert c.patch(f'/api/responsibles/{id}',json={'operational_selectable':False}).status_code==200
    assert id in [r['id'] for r in c.get('/api/responsibles?include_inactive=true').json()]
    assert id not in [r['id'] for r in c.get('/api/responsibles?operational_only=true').json()]
    assert other in [r['id'] for r in c.get('/api/responsibles?operational_only=true').json()]
    account_role(f,admin,grants=['catalogs.responsibles.edit'])
    assert c.patch(f'/api/responsibles/{id}',json={'operational_selectable':True}).status_code==200
    assert c.post(f'/api/responsibles/{id}/access',json={}).status_code==403
    account_role(f,admin,grants=['accounts.manage'])
    assert c.patch(f'/api/responsibles/{id}',json={'operational_selectable':False}).status_code==403


def test_selectable_migration_preserves_identity_and_downgrade(postgres_engine):
    from uuid import uuid4
    from test_e2e_update_migration import cli
    database='selectable_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn: conn.execute(text('CREATE DATABASE '+database))
    engine=create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url,'upgrade','0031_role_permissions')
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO responsibles (id,name,username,password_hash,security_role_id,access_granted) SELECT 1,'Admin histórico','admin-dev','hash-sin-cambiar',id,true FROM security_roles WHERE code='SUPERADMIN'"))
            before=conn.scalar(text('SELECT to_jsonb(r) FROM responsibles r WHERE id=1'))
        cli(engine.url,'upgrade','0032_responsible_selectable')
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT operational_selectable FROM responsibles WHERE id=1')) is True
            assert conn.scalar(text("SELECT to_jsonb(r) - 'operational_selectable' FROM responsibles r WHERE id=1"))==before
        cli(engine.url,'downgrade','0031_role_permissions')
        with engine.connect() as conn: assert conn.scalar(text('SELECT to_jsonb(r) FROM responsibles r WHERE id=1'))==before
        cli(engine.url,'upgrade','head')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn: conn.execute(text('DROP DATABASE '+database))
