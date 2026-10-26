"""Phase 2 negative/direct API tests, using disposable PostgreSQL and real sessions."""
from dataclasses import replace
from unittest.mock import patch
import re
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole, SecurityRolePermission, SecurityAudit
from ticketyn.security.permissions import PERMISSIONS, DEFAULT_GRANTS, EXCLUSIVE, normalize_permissions
from ticketyn.security.routes import RULES, resolve, allowed, validate_coverage
from ticketyn.security import roles
from ticketyn.security.service import principal, seed_foundation
from test_security_foundation import security_client, make_account, login, authorize
from security_helpers import fixture_password


def account_role(factory, id, *, role=None, grants=()):
    with factory() as s:
        if role:
            item=s.scalar(select(SecurityRole).where(SecurityRole.code==role))
        else:
            item=SecurityRole(name='Custom scope '+str(s.scalar(select(func.count()).select_from(SecurityRole))));s.add(item);s.flush()
            s.add_all(SecurityRolePermission(role_id=item.id,permission_code=p) for p in normalize_permissions(grants))
        s.get(Responsible,id).security_role_id=item.id
        s.commit()
        return item.id


def concrete(path):
    return re.sub(r'{([^}]+)}',lambda m:{'kind':'activations','event_key':'FMS_ACTIVATION_REGISTERED','format':'pdf'}.get(m[1],'999999'),path)


@pytest.mark.parametrize('role', ['SUPERADMIN','ADMIN','OPERATOR','AUDITOR','CUSTOM'])
def test_closed_inventory_anonymous_and_denied_actions(security_client,role):
    client,app,factory=security_client
    validate_coverage(app)
    make_account(factory,role=role)
    authorize(client,login(client))
    grants=frozenset(client.get('/api/auth/me').json()['permissions'])
    assert (EXCLUSIVE<=grants)==(role=='SUPERADMIN')
    if role in {'OPERATOR','AUDITOR'}:
        assert not any(p.startswith(('mail.','settings.')) or p in {'accounts.manage','roles.manage','security.configure'} for p in grants)
    if role=='OPERATOR':
        assert grants & {p for p in PERMISSIONS if p.startswith('changes.')} == {'changes.view','changes.export'}
    for (method,path),rule in RULES.items():
        target=concrete(path)
        resolved=resolve(method,target)
        assert resolved is not None
        if rule.public or rule.self_service:continue
        if not allowed(rule,grants,resolved[2],path):
            response=client.request(method,target,**({'json':{}} if method in {'POST','PATCH'} else {}))
            assert response.status_code==(401 if path.endswith('/oauth/callback') else 403),(role,method,path,response.text)
    # A valid session (including Superadmin) cannot opt into a new unclassified endpoint.
    @app.get('/api/unclassified',include_in_schema=False)
    def unsafe():return {'leak':True}
    assert client.get('/api/unclassified').status_code==403
    assert client.get('/api/customers').status_code==(403 if role=='CUSTOM' else 200)
    client.headers.pop('Authorization')
    for method,path in RULES:
        if not RULES[(method,path)].public:
            assert client.request(method,concrete(path)).status_code==401,(method,path)


def test_role_contracts_empty_independent_copies_exclusive_and_case(security_client):
    client,app,factory=security_client
    make_account(factory);authorize(client,login(client))
    created=client.post('/api/security/roles',json={'name':'Técnicos'})
    assert created.status_code==201,created.text
    id=created.json()['id'];assert created.json()['permissions']==[]
    assert client.post('/api/security/roles',json={'name':'TÉCNICOS'}).status_code==409
    assert client.post('/api/security/roles',json={'name':'Injected','permissions':['tickets.edit']}).status_code==422
    for permission in [*EXCLUSIVE,'invented.action']:
        assert client.patch(f'/api/security/roles/{id}',json={'permissions':[permission]}).status_code==422
    updated=client.patch(f'/api/security/roles/{id}',json={'permissions':['changes.edit','reports.changes.export']})
    assert updated.status_code==200,updated.text
    assert set(updated.json()['permissions'])=={'changes.view','changes.edit','reports.changes.export'}
    copy=client.post(f'/api/security/roles/{id}/duplicate',json={'name':'Copia'}).json()
    assert copy['permissions']==updated.json()['permissions'] and copy['id']!=id
    assert client.patch(f'/api/security/roles/{id}',json={'permissions':['changes.edit','reports.changes.export']}).json()['permissions']==['reports.changes.export']
    assert client.get(f"/api/security/roles/{copy['id']}").json()['permissions']==copy['permissions']
    for role in client.get('/api/security/roles?limit=200').json():
        if role['code']:
            assert client.patch(f"/api/security/roles/{role['id']}",json={'name':'Override'}).status_code==403
            response=client.post(f"/api/security/roles/{role['id']}/duplicate",json={'name':'Copy '+role['code']})
            assert response.status_code==(403 if role['code'] in {'SUPERADMIN','ADMIN'} else 201),response.text
    assert client.delete(f"/api/security/roles/{copy['id']}").status_code==204


def test_immediate_grants_without_session_activity_and_assigned_role_delete(security_client):
    client,app,factory=security_client
    id=make_account(factory);authorize(client,login(client))
    token=client.headers['Authorization'].removeprefix('Bearer ')
    last=app.state.security.get(token).last_activity
    role_id=account_role(factory,id,grants=['changes.view','reports.changes.export'])
    assert client.get('/api/changes').status_code==200
    assert client.get('/api/sectors').status_code==200 # contextual selector only
    assert client.post('/api/sectors',json={'name':'denied'}).status_code==403
    assert client.post('/api/changes',json={}).status_code==403
    assert client.get('/api/change-reports/summary').status_code==403
    assert client.get('/api/change-reports/export/xlsx').status_code==200
    assert client.get('/api/mail-notifications/smtp').status_code==403
    with factory() as s:
        role=s.get(SecurityRole,role_id)
        s.add(SecurityRolePermission(role_id=role_id,permission_code='changes.create'));role.revision+=1;s.commit()
    assert client.post('/api/changes',json={}).status_code==422 # permission passes, data validation still enforced
    assert app.state.security.get(token).last_activity==last
    with factory() as s:
        # Even corrupt/out-of-contract persisted grants cannot grant exclusives to custom roles.
        s.add(SecurityRolePermission(role_id=role_id,permission_code='roles.manage'));s.commit()
    assert client.get('/api/security/permissions').status_code==403
    assert 'roles.manage' not in client.get('/api/auth/me').json()['permissions']


@pytest.mark.parametrize('role',['ADMIN','OPERATOR','AUDITOR'])
def test_custom_definition_endpoints_exclusive_to_superadmin(security_client,role):
    client,app,factory=security_client;make_account(factory,role=role);authorize(client,login(client))
    for method,path in [('POST','/api/security/roles'),('PATCH','/api/security/roles/1'),('DELETE','/api/security/roles/1'),('POST','/api/security/roles/1/duplicate')]:
        assert client.request(method,path,json={'name':'Elevated'}).status_code==403


def test_account_authority_operational_catalog_and_last_superadmin(security_client):
    client,app,factory=security_client
    id=make_account(factory);authorize(client,login(client))
    assert client.patch(f'/api/responsibles/{id}',json={'active':False}).status_code==409
    account_role(factory,id,role='ADMIN')
    assert client.patch(f'/api/responsibles/{id}',json={'active':False}).status_code==403
    # Changing descriptive operational data cannot change credentials/role.
    assert client.patch(f'/api/responsibles/{id}',json={'name':'Nombre corregido'}).status_code==200
    assert client.patch(f'/api/responsibles/{id}',json={'access_granted':False}).status_code==422
    with factory() as s:
        other=Responsible(name='Peer',username='Peer',password_hash='opaque',access_granted=True,security_role_id=s.get(Responsible,id).security_role_id)
        s.add(other);s.flush();other_id=other.id;s.commit()
    assert client.patch(f'/api/responsibles/{other_id}',json={'active':False}).status_code==403
    account_role(factory,id,grants=['catalogs.responsibles.edit'])
    assert client.patch(f'/api/responsibles/{other_id}',json={'active':False}).status_code==403
    assert client.patch(f'/api/responsibles/{other_id}',json={'name':'Operativo'}).status_code==200


def test_role_changes_audited_transactionally_and_safe_account_assignment(security_client):
    client,app,factory=security_client
    id=make_account(factory);authorize(client,login(client))
    with factory() as s:
        actor=principal(s,id)
        with patch('ticketyn.security.service.audit',side_effect=RuntimeError('audit unavailable')):
            with pytest.raises(RuntimeError):roles.create_role(s,actor,'Rol sin auditoría')
            s.rollback()
    with factory() as s:
        assert s.scalar(select(SecurityRole.id).where(SecurityRole.name=='Rol sin auditoría')) is None
        with pytest.raises(HTTPException) as error:roles.assign_role(s,principal(s,id),id,s.scalar(select(SecurityRole.id).where(SecurityRole.code=='ADMIN')))
        assert error.value.status_code==409
        s.rollback()
    created=client.post('/api/security/roles',json={'name':'Custom audit'}).json()
    with factory() as s:
        target=Responsible(name='Target',username='Target',password_hash='opaque',access_granted=False,security_role_id=created['id']);s.add(target);s.commit()
    assert client.delete(f"/api/security/roles/{created['id']}").status_code==409
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.event=='ROLE_CREATED'))==1


def test_cam_combined_fields_and_granular_execution_without_edit(security_client):
    from test_changes import payload
    client,app,factory=security_client
    id=make_account(factory);authorize(client,login(client))
    values=payload(client)
    item=client.post('/api/changes',json=values).json();url=f"/api/changes/{item['id']}"
    account_role(factory,id,role='OPERATOR')
    for body in [{'title':'denied'},{'status':'EXECUTING','actual_start':values['proposed_start']},{'internal_ticket_ids':[]}]:
        assert client.patch(url,json=body).status_code==403
    account_role(factory,id,grants=['changes.edit'])
    assert client.patch(url,json={'title':'Corrección'}).status_code==200
    assert client.patch(url,json={'title':'Should roll back','status':'EXECUTING','actual_start':values['proposed_start']}).status_code==403
    assert client.get(url).json()['title']=='Corrección'
    account_role(factory,id,grants=['changes.execute'])
    assert client.patch(url,json={'status':'EXECUTING','actual_start':values['proposed_start']}).status_code==200
    assert client.patch(url,json={'title':'Cannot edit'}).status_code==403
    account_role(factory,id,role='ADMIN')
    assert client.patch(url,json={'title':'Administrado'}).status_code==200


def test_quick_creation_is_scoped_and_does_not_grant_catalog_management(security_client):
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    account_role(factory,id,grants=['context.nodes.create','context.customers.create'])
    node=client.post('/api/nodes',json={'name':'Quick node'})
    assert node.status_code==201,node.text
    assert client.post('/api/nodes',json={'name':'Inactive node','active':False}).status_code==403
    assert client.patch(f"/api/nodes/{node.json()['id']}",json={'name':'Escalate'}).status_code==403
    assert client.post('/api/customers',json={'customer_code':'QUICK','name':'Quick'}).status_code==201
    assert client.post('/api/sectors',json={'name':'Not a quick form'},headers={'Referer':'http://localhost/tickets/new','X-Operation-Context':'tickets'}).status_code==403
    assert client.get('/api/settings/ticket-number').status_code==403


def test_context_relations_return_summary_without_unrelated_private_details(security_client):
    from test_internal_tickets import payload
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    item=client.post('/api/internal-tickets',json=payload(client)).json()
    account_role(factory,id,grants=['changes.link'])
    response=client.get('/api/internal-tickets')
    assert response.status_code==200 and set(response.json()[0])=={'id','reference','title'}
    response=client.get(f"/api/internal-tickets/{item['id']}")
    assert set(response.json())=={'id','reference','title'}
    assert client.get(f"/api/internal-tickets/{item['id']}/updates").status_code==403


def test_mime_and_oauth_routes_remain_separate_from_operational_notify(security_client):
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    account_role(factory,id,grants=['activations.notify'])
    for method,path in [('GET','/api/mail-notifications/smtp'),('PATCH','/api/mail-notifications/oauth'),('POST','/api/mail-notifications/smtp/test'),('POST','/api/mail-notifications/oauth/authorize'),('POST','/api/mail-notifications/processor/resume')]:
        assert client.request(method,path,json={}).status_code==403
    assert client.post('/api/activations/999999/notification',json={'revision':0}).status_code==404


def test_dependency_removal_and_export_independence():
    assert normalize_permissions(['changes.edit'])=={'changes.view','changes.edit'}
    assert normalize_permissions(['changes.edit'],['changes.view','changes.edit'])==set()
    assert normalize_permissions(['reports.changes.export'])=={'reports.changes.export'}
    for role,grants in DEFAULT_GRANTS.items():
        assert grants<=PERMISSIONS.keys(),(role,grants-PERMISSIONS.keys())


def test_operator_existing_ticket_operations_auditor_and_independent_export(security_client,ticket_payload):
    client,app,factory=security_client;id=make_account(factory,role='OPERATOR');authorize(client,login(client))
    created=client.post('/api/tickets',json=ticket_payload)
    assert created.status_code==201,created.text
    url=f"/api/tickets/{created.json()['id']}"
    assert client.patch(url,json={'title':'Operación vigente'}).status_code==200
    assert client.patch(url,json={'status':'CLOSED','end_at':'2020-01-01T13:00:00Z'}).status_code==200
    account_role(factory,id,role='AUDITOR')
    assert client.get(url).status_code==200
    assert client.patch(url,json={'title':'Prohibido'}).status_code==403
    account_role(factory,id,grants=['tickets.close'])
    assert client.patch(url,json={'status':'OPEN'}).status_code==200
    assert client.patch(url,json={'status':'CLOSED','title':'Escalación indirecta'}).status_code==403
    assert client.get(url).json()['status']=='OPEN'
    account_role(factory,id,grants=['tickets.view'])
    assert client.get('/api/tickets/export/xlsx').status_code==403
    account_role(factory,id,grants=['tickets.export'])
    assert client.get('/api/tickets/export/xlsx').status_code==200
    assert client.get('/api/tickets').status_code==403


def test_circuit_combined_mutations_and_operational_cpe_scope(security_client,ticket_payload):
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    new_sector=client.post('/api/sectors',json={'name':'Sector nuevo permiso'}).json()['id']
    cid=ticket_payload['circuit_id'];url=f'/api/circuits/{cid}'
    account_role(factory,id,grants=['circuits.edit'])
    assert client.patch(url,json={'description':'Corrección autorizada'}).status_code==200
    assert client.patch(url,json={'sector_id':new_sector,'description':'No debe persistir'}).status_code==403
    assert client.get(url).json()['description']=='Corrección autorizada'
    assert client.patch(url,json={'active':False}).status_code==403
    assert client.patch(url+'/cpe-configuration',json={'configuration':'secret config'}).status_code==403
    account_role(factory,id,grants=['cpe.edit'])
    assert client.patch(url+'/cpe-configuration',json={'configuration':'config técnica'}).status_code==200
    assert client.patch(url,json={'description':'CPE no autoriza circuito'}).status_code==403
    assert client.get('/api/cpe-models').status_code==200
    assert client.post('/api/cpe-models',json={'name':'No autorizado'}).status_code==403


def test_context_initial_activation_and_mail_template_read_redactions(security_client,ticket_payload):
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    with factory() as s:
        responsible=s.scalar(select(Responsible).where(Responsible.username=='Tester'));rid=responsible.id
    response=client.post('/api/activations',json={'circuit_id':ticket_payload['circuit_id'],'customer_id':ticket_payload['customer_id'],'responsible_id':rid,'effective_at':'2026-01-01T12:00:00Z','activation_notes':'Notas históricas privadas'})
    assert response.status_code==201,response.text
    events=client.get('/api/mail-notifications/events').json();key=events[0]['event_key']
    assert client.patch('/api/mail-notifications/events/'+key,json={'to':['configured@example.com']}).status_code==200
    account_role(factory,id,grants=['circuits.view','mail.templates.view'])
    detail=client.get(f"/api/circuits/{ticket_payload['circuit_id']}/operational-detail").json()
    assert detail['initial_activation'] is None
    assert 'Notas históricas privadas' not in str(detail)
    event=client.get('/api/mail-notifications/events/'+key)
    assert event.status_code==200 and event.json()['to']==[]
    assert client.get('/api/activations').status_code==403
    account_role(factory,id,grants=['mail.templates.preview'])
    assert client.get('/api/activations').status_code==200
    assert client.get('/api/mail-notifications/smtp').status_code==403


def test_callback_rechecks_current_permissions_of_bound_session(security_client):
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    callback='/api/mail-notifications/oauth/callback'
    app.state.security.bind_flow('test-binding',app.state.security.get(client.headers['Authorization'][7:]))
    client.cookies.set('ticketyn_mail_oauth_binding','test-binding',path=callback)
    account_role(factory,id,role='OPERATOR')
    # Live cookie binding is necessary but does not replace the current permission check.
    assert client.get(callback+'?state=x&code=y',follow_redirects=False).status_code==403


from test_ticket_concurrency import concurrent_database

def test_role_name_creation_serializes_between_process_connections(concurrent_database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from security_helpers import fixture_password
    engine,_=concurrent_database
    with Session(engine) as s:
        seed_foundation(s)
        role_id=s.scalar(select(SecurityRole.id).where(SecurityRole.code=='SUPERADMIN'))
        account=Responsible(name='Concurrent admin',username='concurrent-admin',password_hash=fixture_password(),access_granted=True,security_role_id=role_id)
        s.add(account);s.flush();id=account.id;s.commit()
    barrier=Barrier(2)
    def create():
        with Session(engine) as s:
            actor=principal(s,id);barrier.wait(timeout=10)
            try:
                row=roles.create_role(s,actor,'Concurrent custom');s.commit();return row.id
            except HTTPException as error:
                s.rollback();assert error.status_code==409;return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:create(),range(2)))
    assert sum(value is not None for value in results)==1
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(SecurityRole).where(SecurityRole.name=='Concurrent custom'))==1
        assert s.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.event=='ROLE_CREATED'))==1


def test_read_only_context_requires_a_real_relationship(security_client,ticket_payload):
    from test_internal_tickets import payload as internal_payload
    from test_changes import payload as change_payload
    client,app,factory=security_client;id=make_account(factory);authorize(client,login(client))
    body=internal_payload(client)
    linked=client.post('/api/internal-tickets',json=body).json()['id']
    other=client.post('/api/internal-tickets',json={**body,'title':'Solo vinculado a CAM'}).json()['id']
    ticket=client.post('/api/tickets',json={**ticket_payload,'internal_ticket_id':linked})
    assert ticket.status_code==201,ticket.text
    change=client.post('/api/changes',json={**change_payload(client),'internal_ticket_ids':[other]})
    assert change.status_code==201,change.text
    account_role(factory,id,grants=['tickets.view'])
    response=client.get(f'/api/internal-tickets/{linked}')
    assert response.status_code==200 and set(response.json())=={'id','reference','title'}
    assert client.get(f'/api/internal-tickets/{other}').status_code==403
    assert client.get('/api/internal-tickets').status_code==403
    account_role(factory,id,grants=['changes.view'])
    assert client.get(f'/api/internal-tickets/{other}').status_code==200
    assert client.get(f'/api/internal-tickets/{linked}').status_code==403
    account_role(factory,id,grants=['tickets.link'])
    assert client.get(f'/api/internal-tickets/{other}').status_code==200
    assert client.get('/api/internal-tickets').status_code==200


def test_custom_operator_copy_role_with_create_denies_edit_execute_link_and_followup(security_client):
    from test_changes import payload
    client, app, factory = security_client
    # Preserve the historical 72-permission scope; v0.8 explicitly adds distribution
    # to the built-in Operator, without changing previously copied custom roles.
    operator_grants = DEFAULT_GRANTS['OPERATOR']
    legacy_operator_grants = {code for code in operator_grants if not code.startswith(('distribution_devices.', 'distribution_ports.', 'catalogs.port_nomenclatures.', 'catalogs.distribution_device_templates.'))}
    assert len(legacy_operator_grants) == 72
    assert 'changes.create' not in operator_grants
    assert 'changes.view' in operator_grants
    assert 'changes.export' in operator_grants

    # Preparar cuenta administrativa para crear la ventana y registrar dependencias
    admin_id = make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))
    values = payload(client)
    created_change = client.post('/api/changes', json=values).json()
    cid = created_change['id']
    url = f"/api/changes/{cid}"

    # Crear cuenta para ANDRES con rol personalizado 'Operador (copia)' (73 permisos)
    custom_grants = list(legacy_operator_grants) + ['changes.create']
    assert len(custom_grants) == 73

    with factory() as s:
        custom_role = SecurityRole(name='Operador (copia)')
        s.add(custom_role)
        s.flush()
        s.add_all(SecurityRolePermission(role_id=custom_role.id, permission_code=p) for p in normalize_permissions(custom_grants))
        andres_account = Responsible(
            name='ANDRES', username='andres', active=True, access_granted=True,
            password_hash=fixture_password(), password_change_required=False,
            security_role_id=custom_role.id
        )
        s.add(andres_account)
        s.commit()

    # Iniciar sesión como andres
    authorize(client, login(client, username='andres'))
    me = client.get('/api/auth/me').json()
    assert len(me['permissions']) == 73
    assert not any(code.startswith(('distribution_devices.', 'distribution_ports.')) for code in me['permissions'])
    assert 'changes.create' in me['permissions']
    assert 'changes.view' in me['permissions']
    assert 'changes.export' in me['permissions']
    assert not any(p in me['permissions'] for p in ('changes.edit', 'changes.execute', 'changes.link', 'changes.followup'))

    # 1. GET /api/changes -> HTTP 200
    assert client.get('/api/changes').status_code == 200
    assert client.get(url).status_code == 200

    # 2. Exportación autorizada -> HTTP 200
    assert client.get('/api/changes/export/pdf').status_code == 200
    assert client.get('/api/changes/export/xlsx').status_code == 200
    assert client.get(f"{url}/reports/pdf").status_code == 200
    assert client.get('/api/change-reports/export/pdf').status_code == 200

    # 3. POST /api/changes con datos válidos -> creación autorizada
    new_values = {**values, 'title': 'Ventana creada por ANDRES'}
    created_by_andres = client.post('/api/changes', json=new_values)
    assert created_by_andres.status_code == 201, created_by_andres.text
    assert created_by_andres.json()['title'] == 'Ventana creada por ANDRES'

    # Snapshot del registro original antes de operaciones rechazadas
    initial_snapshot = client.get(url).json()

    # 4. PATCH /api/changes/{id} para modificar datos generales -> HTTP 403
    assert client.patch(url, json={'title': 'Título modificado no autorizado'}).status_code == 403
    # 8. Verificar que permanezca intacto
    assert client.get(url).json()['title'] == initial_snapshot['title']

    # 5. PATCH /api/changes/{id} para modificar estado o ejecución -> HTTP 403
    assert client.patch(url, json={'status': 'EXECUTING', 'actual_start': values['proposed_start']}).status_code == 403
    # 8. Verificar que permanezca intacto
    after_exec = client.get(url).json()
    assert after_exec['status'] == initial_snapshot['status']
    assert after_exec['actual_start'] == initial_snapshot['actual_start']

    # 6. PATCH /api/changes/{id} para gestionar vínculos -> HTTP 403
    assert client.patch(url, json={'internal_ticket_ids': []}).status_code == 403
    # 8. Verificar que permanezca intacto
    assert client.get(url).json()['internal_tickets'] == initial_snapshot['internal_tickets']

    # 7. POST /api/changes/{id}/updates -> HTTP 403
    assert client.post(f"{url}/updates", json={
        'responsible_id': values['manager_id'],
        'content': 'Seguimiento no autorizado',
        'occurred_at': values['proposed_start']
    }).status_code == 403
    # 8. Verificar que permanezca intacto
    assert client.get(f"{url}/updates").json()['total'] == 0
