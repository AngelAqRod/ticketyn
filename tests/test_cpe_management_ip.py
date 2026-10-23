"""CPE host addresses: existing circuit contracts and isolated PostgreSQL."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole
from ticketyn.schemas.circuit import CircuitUpdate
from test_e2e_update_migration import cli
from test_fms import operation_payload


@pytest.mark.parametrize('value', ['192.168.1.300', '192.168.1.0/24', '2001:db8::/64',
    '192.0.2.1/32', '::1/128', 'cpe01.example.net', '10.20.30.40 pendiente',
    '192.168.1.10,192.168.1.11', 'fe80::1%eth0', 1234, True, [], {}])
def test_invalid_addresses(api_client, ticket_payload, value):
    cid = ticket_payload['circuit_id']
    response = api_client.patch(f'/api/circuits/{cid}', json={'cpe_management_ip': value})
    assert response.status_code == 422
    assert response.json()['detail'][0]['loc'] == ['body', 'cpe_management_ip']
    assert api_client.get(f'/api/circuits/{cid}').json()['cpe_management_ip'] is None
    payload = {key: ticket_payload[key] for key in ('node_id', 'sector_id', 'customer_id')}
    assert api_client.post('/api/circuits', json={**payload, 'circuit_code': 'INVALID',
        'description': 'Inválido', 'cpe_management_ip': value}).status_code == 422


@pytest.mark.parametrize('value, expected', [(None, None), ('', None), ('  ', None),
    ('192.168.1.10', '192.168.1.10'), ('10.20.30.40', '10.20.30.40'),
    ('2001:0DB8:0000:0000:0000:0000:0000:0010', '2001:db8::10'),
    ('::1', '::1'), ('0.0.0.0', '0.0.0.0'), (' 192.0.2.10 ', '192.0.2.10')])
def test_create_read_list_and_non_unique_ip(api_client, ticket_payload, value, expected):
    payload = {key: ticket_payload[key] for key in ('node_id', 'sector_id', 'customer_id')}
    for index in range(2):
        response = api_client.post('/api/circuits', json={**payload, 'circuit_code': f'IP-{index}',
            'description': 'IP de gestión', 'cpe_management_ip': value})
        assert response.status_code == 201, response.text
        item = response.json()
        assert item['cpe_management_ip'] == expected
        assert api_client.get(f"/api/circuits/{item['id']}").json()['cpe_management_ip'] == expected
        listed = api_client.get('/api/circuits').json()
        assert next(row for row in listed if row['id'] == item['id'])['cpe_management_ip'] == expected
        detail = api_client.get(f"/api/circuits/{item['id']}/operational-detail").json()
        assert detail['circuit']['cpe_management_ip'] == expected


@pytest.mark.parametrize('empty', [None, '', '  '])
def test_patch_preserves_omitted_and_clears_explicit(api_client, ticket_payload, empty):
    path = f"/api/circuits/{ticket_payload['circuit_id']}"
    assert api_client.get(path).json()['cpe_management_ip'] is None
    assert api_client.patch(path, json={'cpe_management_ip': '192.0.2.1'}).json()['cpe_management_ip'] == '192.0.2.1'
    assert api_client.patch(path, json={'description': 'Cambio independiente'}).json()['cpe_management_ip'] == '192.0.2.1'
    assert api_client.patch(path, json={'cpe_management_ip': '2001:DB8::2'}).json()['cpe_management_ip'] == '2001:db8::2'
    assert api_client.patch(path, json={'cpe_management_ip': empty}).json()['cpe_management_ip'] is None
    assert CircuitUpdate().model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize('role', ['SUPERADMIN', 'ADMIN', 'OPERATOR', 'AUDITOR'])
def test_existing_circuit_permissions(api_client, ticket_payload, db_session, role):
    account = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    account.security_role_id = db_session.scalar(select(SecurityRole.id).where(SecurityRole.code == role))
    db_session.commit()
    path = f"/api/circuits/{ticket_payload['circuit_id']}"
    assert api_client.get(path).status_code == 200
    assert api_client.patch(path, json={'cpe_management_ip': '192.0.2.1'}).status_code == (403 if role == 'AUDITOR' else 200)
    payload = {key: ticket_payload[key] for key in ('node_id', 'sector_id', 'customer_id')}
    assert api_client.post('/api/circuits', json={**payload, 'circuit_code': 'ROLE',
        'description': 'Permisos', 'cpe_management_ip': '::1'}).status_code == (403 if role == 'AUDITOR' else 201)
    api_client.headers.pop('Authorization')
    assert api_client.get(path).status_code == 401
    assert api_client.patch(path, json={'cpe_management_ip': None}).status_code == 401


def test_0035_additive_migration_roundtrip(postgres_engine):
    name = 'cpe_ip_migration_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0034_activation_distribution')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers(name,customer_code) VALUES ('Histórico','OLD')"))
            connection.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'OLD','Sin IP')"))
            before = connection.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
        cli(engine.url, 'upgrade', '0035_cpe_management_ip')
        with engine.begin() as connection:
            row = connection.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
            assert row.pop('cpe_management_ip') is None
            assert row == before
            column = next(c for c in inspect(connection).get_columns('circuits') if c['name'] == 'cpe_management_ip')
            assert str(column['type']) == 'INET' and column['nullable'] and column['default'] is None
            connection.execute(text("UPDATE circuits SET cpe_management_ip='2001:db8::10'"))
            assert str(connection.scalar(text('SELECT cpe_management_ip FROM circuits'))) == '2001:db8::10'
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("UPDATE circuits SET cpe_management_ip='192.0.2.0/24'"))
        with pytest.raises(AssertionError, match='Downgrade inseguro'):
            cli(engine.url, 'downgrade', '0034_activation_distribution')
        with engine.begin() as connection:
            connection.execute(text('UPDATE circuits SET cpe_management_ip=NULL'))
        cli(engine.url, 'downgrade', '0034_activation_distribution')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT to_jsonb(c) FROM circuits c')) == before
        cli(engine.url, 'upgrade', '0035_cpe_management_ip')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))


def test_ip_changes_do_not_rewrite_or_create_fms_records(api_client, operation_payload, db_session):
    from test_fms import create
    create(api_client, '/api/activations', operation_payload)
    create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'INCREASE',
        'new_capacity': '100', 'new_unit': 'Mbps'})
    tables = ('activations', 'capacity_changes', 'circuit_lifecycle_operations')
    def snapshots():
        return {table: db_session.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all()
                for table in tables}
    before = snapshots()
    path = f"/api/circuits/{operation_payload['circuit_id']}"
    for value in ('192.0.2.1', '2001:db8::10', None):
        assert api_client.patch(path, json={'cpe_management_ip': value}).status_code == 200
        assert snapshots() == before
