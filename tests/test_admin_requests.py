from datetime import date
import pytest
from sqlalchemy import select
from ticketyn.models import AdminRequest, Responsible
from ticketyn.security.routes import allowed, resolve

BASE = '/api/admin-requests'


@pytest.fixture
def ctx(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'Solicitantes'}).json()['id']
    person = api_client.post('/api/responsibles', json={'name': 'Solicitante sin portal', 'department_id': dept}).json()
    kind = api_client.post('/api/admin-request-types', json={'name': 'Asignación de IP pública'})
    assert kind.status_code == 201, kind.text
    return {'client': api_client, 'tp': ticket_payload, 'person': person['id'], 'type': kind.json()['id'],
            'body': {'request_date': '2026-11-10', 'requester_id': person['id'], 'type_id': kind.json()['id'], 'description': 'Asignar IP pública'}}


def make(ctx, **extra):
    r = ctx['client'].post(BASE, json={**ctx['body'], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_edit_and_server_owned_fields(ctx, db_session):
    c = ctx['client']
    item = make(ctx)
    assert item['reference'] == 'SOL-0000001' and item['customer'] is None and item['circuit'] is None
    assert item['requester']['name'] == 'Solicitante sin portal' and item['registered_by']['id'] == c.app.state.test_security_account_id
    assert item['request_date'] == '2026-11-10' and item['created_at']
    created = item['created_at']
    for bad in ({'requester_id': None}, {'description': ' '}, {'type_id': 999999}, {'requester_id': 999999}, {'ticket_number': 5}):
        assert c.post(BASE, json={**ctx['body'], **bad}).status_code in (422,), bad
    assert c.post(BASE, json={k: v for k, v in ctx['body'].items() if k != 'requester_id'}).status_code == 422
    # editable date, earlier or later than today; registration date is untouched
    for new in ('2020-01-01', '2999-12-31'):
        r = c.patch(f"{BASE}/{item['id']}", json={'request_date': new, 'notes': 'Nota'})
        assert r.status_code == 200 and r.json()['request_date'] == new and r.json()['created_at'] == created
    assert c.patch(f"{BASE}/{item['id']}", json={'created_at': '2020-01-01T00:00:00Z'}).status_code == 422
    assert c.patch(f"{BASE}/{item['id']}", json={'description': None}).status_code == 422
    assert {'CREATE', 'EDIT'} <= {e['action'] for e in c.get(f"{BASE}/{item['id']}").json()['events']}


def test_requester_with_and_without_portal_access(ctx, db_session):
    c = ctx['client']
    admin = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    assert admin.access_granted and make(ctx, requester_id=admin.id)['requester']['id'] == admin.id
    assert make(ctx)['requester']['id'] == ctx['person']
    admin.operational_selectable = False
    db_session.flush()
    assert c.post(BASE, json={**ctx['body'], 'requester_id': admin.id}).status_code == 422


def test_customer_circuit_rules(ctx):
    c, tp = ctx['client'], ctx['tp']
    other = c.post('/api/customers', json={'customer_code': 'OTRO', 'name': 'Otro cliente'}).json()['id']
    assert make(ctx, customer_id=tp['customer_id'])['circuit'] is None
    assert c.post(BASE, json={**ctx['body'], 'customer_id': other, 'circuit_id': tp['circuit_id']}).status_code == 422
    both = make(ctx, customer_id=tp['customer_id'], circuit_id=tp['circuit_id'])
    assert both['circuit']['id'] == tp['circuit_id']
    assert make(ctx, circuit_id=tp['circuit_id'])['customer']['id'] == tp['customer_id']
    assert c.patch(f"{BASE}/{both['id']}", json={'customer_id': other}).status_code == 422
    cleared = c.patch(f"{BASE}/{both['id']}", json={'customer_id': None, 'circuit_id': None})
    assert cleared.status_code == 200 and cleared.json()['customer'] is None and cleared.json()['circuit'] is None


def tickets(ctx, *starts, circuit_id=None):
    tp = {**ctx['tp'], **({'circuit_id': circuit_id} if circuit_id else {})}
    return [ctx['client'].post('/api/tickets', json={**tp, 'start_at': s}).json() for s in starts]


def candidates(ctx, item, path, **params):
    r = ctx['client'].get(f"{BASE}/{item['id']}/candidates/{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_ticket_window_is_inclusive_and_filters_by_circuit(ctx):
    c, tp = ctx['client'], ctx['tp']
    node, sector = tp['node_id'], tp['sector_id']
    second = c.post('/api/circuits', json={'node_id': node, 'sector_id': sector, 'customer_id': tp['customer_id'], 'circuit_code': 'OTRO-CIRCUITO', 'description': 'x'}).json()['id']
    first, last, before, after = tickets(ctx, '2026-10-26T00:00:00-06:00', '2026-11-25T23:59:59-06:00', '2026-10-25T23:59:59-06:00', '2026-11-26T00:00:00-06:00')
    elsewhere, = tickets(ctx, '2026-11-10T12:00:00-06:00', circuit_id=second)
    by_customer = candidates(ctx, make(ctx, customer_id=tp['customer_id']), 'tickets')
    assert {t['id'] for t in by_customer['items']} == {first['id'], last['id'], elsewhere['id']} and by_customer['total'] == 3
    by_circuit = candidates(ctx, make(ctx, circuit_id=tp['circuit_id']), 'tickets')
    assert {t['id'] for t in by_circuit['items']} == {first['id'], last['id']}
    page = candidates(ctx, make(ctx, circuit_id=tp['circuit_id']), 'tickets', limit=1, offset=1)
    assert page['total'] == 2 and len(page['items']) == 1
    assert candidates(ctx, make(ctx, circuit_id=tp['circuit_id']), 'tickets', search='no-existe')['total'] == 0


def test_all_kinds_link_without_duplicates_and_survive_date_change(ctx):
    c, tp = ctx['client'], ctx['tp']
    internal = c.post('/api/internal-tickets', json={'title': 'Interno', 'description': 'd', 'sector_id': tp['sector_id'], 'department_id': tp['department_id'],
        'incident_type_id': c.post('/api/internal-incident-types', json={'name': 'Energía'}).json()['id'], 'start_at': '2026-11-10T08:00:00-06:00'}).json()
    far_internal = c.post('/api/internal-tickets', json={'title': 'Lejano', 'description': 'd', 'sector_id': tp['sector_id'], 'department_id': tp['department_id'],
        'incident_type_id': internal['incident_type_id'], 'start_at': '2026-09-01T08:00:00-06:00'}).json()
    manager = c.post('/api/responsibles', json={'name': 'Encargado', 'department_id': tp['department_id']}).json()['id']
    kind = c.post('/api/change-types', json={'name': 'Tipo'}).json()['id']
    def change(start):
        r = c.post('/api/changes', json=dict(change_type_id=kind, title='Cambio', description='d', sector_id=tp['sector_id'], manager_id=manager, proposed_start=start, proposed_end=start.replace('11:00', '12:00')))
        assert r.status_code == 201, r.text
        return r.json()
    near, far = change('2026-11-25T11:00:00-06:00'), change('2026-12-30T11:00:00-06:00')
    ticket, = tickets(ctx, '2026-11-12T10:00:00-06:00')
    item = make(ctx)
    ids = lambda path: {x['id'] for x in candidates(ctx, item, path)['items']}
    assert ids('internal-tickets') == {internal['id']} and ids('changes') == {near['id']}
    for kind_name, target in (('ticket', ticket['id']), ('internal_ticket', internal['id']), ('change', near['id'])):
        r = c.post(f"{BASE}/{item['id']}/links", json={'kind': kind_name, 'target_id': target})
        assert r.status_code == 201, r.text
        assert c.post(f"{BASE}/{item['id']}/links", json={'kind': kind_name, 'target_id': target}).status_code == 409
    assert c.post(f"{BASE}/{item['id']}/links", json={'kind': 'change', 'target_id': 999999}).status_code == 422
    # a link outside the window is still shown after the request date moves
    c.post(f"{BASE}/{item['id']}/links", json={'kind': 'internal_ticket', 'target_id': far_internal['id']})
    moved = c.patch(f"{BASE}/{item['id']}", json={'request_date': '2027-06-01'}).json()
    assert [x['id'] for x in moved['links']['tickets']] == [ticket['id']] and len(moved['links']['internal_tickets']) == 2
    assert [x['id'] for x in moved['links']['changes']] == [near['id']] and far['id'] not in ids('changes')
    link = moved['links']['changes'][0]['link_id']
    assert c.delete(f"{BASE}/{item['id']}/links/{link}").json()['links']['changes'] == []
    assert c.delete(f"{BASE}/{item['id']}/links/{link}").status_code == 404
    assert c.post(f"{BASE}/{item['id']}/links", json={'kind': 'change', 'target_id': near['id']}).status_code == 201


def test_listing_filters_and_number_settings(ctx):
    c, tp = ctx['client'], ctx['tp']
    a = make(ctx, request_date='2026-01-05', customer_id=tp['customer_id'])
    b = make(ctx, request_date='2026-03-05', circuit_id=tp['circuit_id'])
    listing = lambda **p: c.get(BASE, params=p).json()
    assert [i['id'] for i in listing(date_from='2026-02-01')['items']] == [b['id']]
    assert [i['id'] for i in listing(date_to='2026-01-05')['items']] == [a['id']]
    assert listing(requester_id=ctx['person'])['total'] == 2 and listing(requester_id=2147000000)['total'] == 0
    assert listing(type_id=ctx['type'], customer_id=tp['customer_id'])['total'] == 2
    assert listing(circuit_id=tp['circuit_id'])['total'] == 1 and listing(search=a['reference'])['total'] == 1
    assert c.get('/api/settings/admin-request-number').json()['prefix'] == 'SOL'
    assert c.patch('/api/settings/admin-request-number', json={'prefix': 'ADM', 'next_number': 50, 'padding': 3}).status_code == 200
    assert make(ctx)['reference'] == 'ADM-050'
    assert c.patch('/api/settings/admin-request-number', json={'next_number': 2}).status_code == 409


def test_permissions_per_route():
    def granted(method, path, *codes):
        template, rule, params = resolve(method, path)
        return allowed(rule, set(codes), params, template)
    assert not granted('POST', '/api/admin-requests')
    assert granted('POST', '/api/admin-requests', 'admin_requests.create')
    assert not granted('PATCH', '/api/admin-requests/1', 'admin_requests.view')
    assert not granted('POST', '/api/admin-requests/1/links', 'admin_requests.edit')
    assert granted('DELETE', '/api/admin-requests/1/links/2', 'admin_requests.link')
    for path, module in (('tickets', 'tickets'), ('internal-tickets', 'internal_tickets'), ('changes', 'changes')):
        url = f'/api/admin-requests/1/candidates/{path}'
        assert not granted('GET', url, 'admin_requests.link') and not granted('GET', url, module + '.view')
        assert granted('GET', url, 'admin_requests.link', module + '.view')
    assert granted('GET', '/api/admin-request-types', 'catalogs.admin_request_types.lookup')
    assert not granted('POST', '/api/admin-request-types', 'catalogs.admin_request_types.lookup')


def test_operator_defaults_are_scoped_to_requests_only():
    from ticketyn.security.permissions import DEFAULT_GRANTS, expanded_context
    operator = DEFAULT_GRANTS['OPERATOR']
    assert {f'admin_requests.{a}' for a in ('view', 'create', 'edit', 'link')} <= operator
    assert not {c for c in operator if c.startswith(('catalogs.admin_request_types.', 'settings.admin_request_number.'))}
    assert not {c for c in DEFAULT_GRANTS['AUDITOR'] if 'admin_request' in c}
    effective = expanded_context(operator)
    assert {'customers.lookup', 'circuits.lookup', 'catalogs.responsibles.lookup', 'catalogs.admin_request_types.lookup'} <= effective
    assert not {c for c in effective if c.startswith(('catalogs.admin_request_types.create', 'catalogs.admin_request_types.edit', 'settings.admin_request_number.'))}
    for method, path in (('GET', '/api/admin-requests'), ('POST', '/api/admin-requests'), ('PATCH', '/api/admin-requests/1'), ('POST', '/api/admin-requests/1/links'),
                         ('DELETE', '/api/admin-requests/1/links/2'), ('GET', '/api/admin-requests/1/candidates/tickets'), ('GET', '/api/admin-requests/1/candidates/internal-tickets'),
                         ('GET', '/api/admin-requests/1/candidates/changes'), ('GET', '/api/admin-request-types')):
        template, rule, params = resolve(method, path)
        assert allowed(rule, effective, params, template), (method, path)
    for method, path in (('POST', '/api/admin-request-types'), ('PATCH', '/api/admin-request-types/1'), ('GET', '/api/settings/admin-request-number'), ('PATCH', '/api/settings/admin-request-number')):
        template, rule, params = resolve(method, path)
        assert not allowed(rule, effective, params, template), (method, path)


def test_existing_installation_operator_gets_new_grants_without_touching_custom_roles(api_client, db_session):
    """Built-in roles resolve from code, so an upgraded OPERATOR row (no stored grants) gains the new permissions."""
    from ticketyn.models.security import SecurityRole, SecurityRolePermission
    from ticketyn.security.roles import role_grants
    operator = db_session.scalar(select(SecurityRole).where(SecurityRole.code == 'OPERATOR'))
    stored = db_session.scalars(select(SecurityRolePermission).where(SecurityRolePermission.role_id == operator.id)).all()
    assert stored == []
    grants = role_grants(db_session, operator)
    assert {f'admin_requests.{a}' for a in ('view', 'create', 'edit', 'link')} <= grants
    assert not {c for c in grants if c.startswith(('catalogs.admin_request_types.', 'settings.admin_request_number.'))}
    custom = SecurityRole(name='Personalizado heredado'); db_session.add(custom); db_session.flush()
    db_session.add(SecurityRolePermission(role_id=custom.id, permission_code='tickets.view')); db_session.flush()
    assert role_grants(db_session, custom) == {'tickets.view'}


def test_status_defaults_transitions_and_history(ctx):
    c = ctx['client']
    item = make(ctx)
    url = f"{BASE}/{item['id']}"
    assert item['status'] == 'REGISTERED'
    assert c.post(f'{url}/status', json={'status': 'COMPLETED'}).status_code == 422  # skipping IN_PROGRESS
    assert c.post(f'{url}/status', json={'status': 'REGISTERED'}).status_code == 422  # same status
    assert c.post(f'{url}/status', json={'status': 'BOGUS'}).status_code == 422
    for new in ('IN_PROGRESS', 'REGISTERED', 'IN_PROGRESS', 'COMPLETED', 'IN_PROGRESS', 'CANCELLED', 'REGISTERED'):
        r = c.post(f'{url}/status', json={'status': new})
        assert r.status_code == 200 and r.json()['status'] == new, new
    assert c.patch(url, json={'status': 'COMPLETED'}).status_code == 422  # status only changes through its route
    events = [e for e in c.get(url).json()['events'] if e['action'] == 'STATUS']
    assert events[0]['detail'] == {'from': 'REGISTERED', 'to': 'IN_PROGRESS'} and len(events) == 7
    assert events[0]['actor_id'] == c.app.state.test_security_account_id and events[0]['created_at']


def test_status_filter(ctx):
    c = ctx['client']
    a, b = make(ctx), make(ctx)
    c.post(f"{BASE}/{b['id']}/status", json={'status': 'IN_PROGRESS'})
    assert [i['id'] for i in c.get(BASE, params={'status': 'IN_PROGRESS'}).json()['items']] == [b['id']]
    assert [i['id'] for i in c.get(BASE, params={'status': 'REGISTERED'}).json()['items']] == [a['id']]
    assert c.get(BASE, params={'status': 'X'}).status_code == 422
    assert len(c.get(BASE).json()['items']) == 2


def test_application_period_is_optional_informative_and_validated(ctx):
    c = ctx['client']
    assert make(ctx)['application_start'] is None
    only_start = make(ctx, application_start='2026-11-20')
    assert only_start['application_start'] == '2026-11-20' and only_start['application_end'] is None
    assert make(ctx, application_end='2026-11-25')['application_start'] is None
    same = make(ctx, application_start='2026-11-20', application_end='2026-11-20')
    assert c.post(BASE, json={**ctx['body'], 'application_start': '2026-11-25', 'application_end': '2026-11-20'}).status_code == 422
    url = f"{BASE}/{same['id']}"
    assert c.patch(url, json={'application_end': '2026-11-19'}).status_code == 422  # merged with the stored start
    assert c.patch(url, json={'application_start': '2026-11-21'}).status_code == 422
    assert c.patch(url, json={'application_start': None, 'application_end': None}).json()['application_end'] is None
    # period and status are independent: completing never needs the period to finish
    done = make(ctx, application_start='2999-01-01', application_end='2999-01-31')
    for new in ('IN_PROGRESS', 'COMPLETED'):
        assert c.post(f"{BASE}/{done['id']}/status", json={'status': new}).json()['status'] == new


def test_status_route_permission():
    def granted(*codes):
        template, rule, params = resolve('POST', '/api/admin-requests/1/status')
        return allowed(rule, set(codes), params, template)
    assert not granted('admin_requests.view') and not granted('admin_requests.link') and granted('admin_requests.edit')
