from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from ticketyn.models import (
    Customer,
    Department,
    InternalEscalation,
    InternalIncidentType,
    InternalTicket,
    Position,
    PositionEscalationDestination,
    Responsible,
    SecurityRole,
    Ticket,
    TicketEscalation,
    TicketUpdate,
)
from ticketyn.models.ack import TicketEscalationAck, InternalTicketEscalationAck
from test_security_foundation import security_client, make_account, login, authorize
from security_helpers import fixture_password


def setup_operator(factory, username, name, role_code='OPERATOR', position_id=None, department_id=None):
    with factory() as session:
        role_id = session.scalar(select(SecurityRole.id).where(SecurityRole.code == role_code))
        acc = Responsible(
            name=name,
            username=username,
            active=True,
            access_granted=True,
            password_hash=fixture_password(),
            password_change_required=False,
            security_role_id=role_id,
            position_id=position_id,
            department_id=department_id,
        )
        session.add(acc)
        session.commit()
        return acc.id, username


def create_internal_ticket(client, sector_id, dept_id, inc_type_id, title='Caída troncal', responsible_id=None):
    res = client.post(
        '/api/internal-tickets',
        json={
            'sector_id': sector_id,
            'department_id': dept_id,
            'incident_type_id': inc_type_id,
            'title': title,
            'description': 'Falla en enlace troncal',
            'start_at': '2026-10-25T10:00:00Z',
            'responsible_id': responsible_id,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()['id']


def test_my_tickets_assigned_and_responsible_transitions(security_client, ticket_payload):
    client, app, factory = security_client

    # Admin creates structure
    make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    dept = client.post('/api/departments', json={'name': 'NOC'}).json()
    pos1 = client.post('/api/positions', json={'name': 'Soporte N1', 'department_id': dept['id']}).json()

    op1_id, op1_user = setup_operator(factory, 'op_alice', 'Alice Operadora', position_id=pos1['id'], department_id=dept['id'])
    op2_id, op2_user = setup_operator(factory, 'op_bob', 'Bob Operador', position_id=pos1['id'], department_id=dept['id'])

    # Create customer ticket assigned to Alice
    payload_cust = {**ticket_payload, 'responsible_id': op1_id, 'title': 'Ticket de Alice'}
    res_cust = client.post('/api/tickets', json=payload_cust)
    assert res_cust.status_code == 201, res_cust.text
    cust_id = res_cust.json()['id']

    # Create internal ticket assigned to Alice
    int_inc = client.post('/api/internal-incident-types', json={'name': 'Fibra'}).json()
    int_id = create_internal_ticket(client, ticket_payload['sector_id'], dept['id'], int_inc['id'], 'Ticket Interno Alice', responsible_id=op1_id)

    # Create ticket assigned to Bob
    payload_bob = {**ticket_payload, 'responsible_id': op2_id, 'title': 'Ticket de Bob'}
    res_bob = client.post('/api/tickets', json=payload_bob)
    bob_cust_id = res_bob.json()['id']

    # Login as Alice
    authorize(client, login(client, username=op1_user))

    # 1. Asignados a mí (Alice)
    res = client.get('/api/my-tickets?view=assigned&status=OPEN')
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['total'] == 2
    refs = {item['id']: item['title'] for item in data['items']}
    assert cust_id in refs
    assert int_id in refs
    assert bob_cust_id not in refs

    # 2. Scope filter: CUSTOMER only
    res = client.get('/api/my-tickets?view=assigned&scope=CUSTOMER')
    assert res.status_code == 200
    data = res.json()
    assert data['total'] == 1
    assert data['items'][0]['id'] == cust_id
    assert data['items'][0]['ticket_type'] == 'CUSTOMER'

    # 3. Scope filter: INTERNAL only
    res = client.get('/api/my-tickets?view=assigned&scope=INTERNAL')
    assert res.status_code == 200
    data = res.json()
    assert data['total'] == 1
    assert data['items'][0]['id'] == int_id
    assert data['items'][0]['ticket_type'] == 'INTERNAL'

    # 4. Search filter
    res = client.get('/api/my-tickets?view=assigned&search=Interno')
    assert res.status_code == 200
    assert res.json()['total'] == 1
    assert res.json()['items'][0]['id'] == int_id

    # 5. Status filter: close internal ticket and check open vs closed
    authorize(client, login(client))  # admin
    client.patch(f'/api/internal-tickets/{int_id}', json={'status': 'CLOSED'})

    authorize(client, login(client, username=op1_user))  # Alice
    res_open = client.get('/api/my-tickets?view=assigned&status=OPEN')
    assert res_open.json()['total'] == 1
    assert res_open.json()['items'][0]['id'] == cust_id

    res_closed = client.get('/api/my-tickets?view=assigned&status=CLOSED')
    assert res_closed.json()['total'] == 1
    assert res_closed.json()['items'][0]['id'] == int_id

    res_all = client.get('/api/my-tickets?view=assigned&status=ALL')
    assert res_all.json()['total'] == 2

    # 6. Change responsible from Alice to Bob -> ticket disappears from Alice's assigned list
    authorize(client, login(client))  # admin
    client.patch(f'/api/tickets/{cust_id}', json={'responsible_id': op2_id})

    authorize(client, login(client, username=op1_user))  # Alice
    res_after = client.get('/api/my-tickets?view=assigned&status=OPEN')
    assert res_after.json()['total'] == 0


def test_my_tickets_participated(security_client, ticket_payload):
    client, app, factory = security_client

    make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    dept = client.post('/api/departments', json={'name': 'NOC'}).json()
    pos1 = client.post('/api/positions', json={'name': 'Soporte N1', 'department_id': dept['id']}).json()

    op1_id, op1_user = setup_operator(factory, 'op_alice2', 'Alice Part', position_id=pos1['id'], department_id=dept['id'])
    op2_id, op2_user = setup_operator(factory, 'op_bob2', 'Bob Resp', position_id=pos1['id'], department_id=dept['id'])

    # Create ticket assigned to Bob
    payload = {**ticket_payload, 'responsible_id': op2_id, 'title': 'Ticket de Bob donde Alice participa'}
    ticket_id = client.post('/api/tickets', json=payload).json()['id']

    # Internal ticket assigned to Bob
    int_inc = client.post('/api/internal-incident-types', json={'name': 'Fibra2'}).json()
    int_id = create_internal_ticket(client, ticket_payload['sector_id'], dept['id'], int_inc['id'], 'Ticket Interno Bob', responsible_id=op2_id)
    esc_reason = client.post('/api/escalation-reasons', json={'name': 'Apoyo técnico'}).json()

    # Alice has not participated yet
    authorize(client, login(client, username=op1_user))
    res = client.get('/api/my-tickets?view=participated')
    assert res.json()['total'] == 0

    # Alice adds a follow-up intervention
    client.post(f'/api/tickets/{ticket_id}/updates', json={'content': 'Primera intervención de Alice', 'visibility': 'INTERNAL', 'responsible_id': op1_id})

    # Alice adds a second intervention on the same ticket
    client.post(f'/api/tickets/{ticket_id}/updates', json={'content': 'Segunda intervención de Alice', 'visibility': 'INTERNAL', 'responsible_id': op1_id})

    # Now Alice sees the ticket in 'participated', without duplicate entries
    res = client.get('/api/my-tickets?view=participated')
    assert res.status_code == 200
    data = res.json()
    assert data['total'] == 1
    assert data['items'][0]['id'] == ticket_id
    assert data['items'][0]['responsible_name'] == 'Bob Resp'

    # Alice creates an escalation on the internal ticket assigned to Bob
    client.post(f'/api/internal-tickets/{int_id}/escalations', json={
        'reason_id': esc_reason['id'],
        'description': 'Alice escala el ticket interno',
        'department_id': dept['id'],
        'requester_id': op1_id,
        'recipient_id': op2_id,
    })

    # Now Alice has participated in both tickets
    res_both = client.get('/api/my-tickets?view=participated')
    assert res_both.json()['total'] == 2
    types = {item['ticket_type'] for item in res_both.json()['items']}
    assert types == {'CUSTOMER', 'INTERNAL'}


def test_my_tickets_escalations_assigned_to_user(security_client, ticket_payload):
    client, app, factory = security_client

    make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    dept = client.post('/api/departments', json={'name': 'NOC'}).json()
    pos_soporte = client.post('/api/positions', json={'name': 'Soporte', 'department_id': dept['id']}).json()
    pos_ingenieria = client.post('/api/positions', json={'name': 'Ingeniería', 'department_id': dept['id']}).json()
    pos_n2 = client.post('/api/positions', json={'name': 'N2 Transporte', 'department_id': dept['id']}).json()

    op_soporte_id, op_soporte_user = setup_operator(factory, 'op_soporte_esc', 'Operador Soporte', position_id=pos_soporte['id'], department_id=dept['id'])
    op_ing1_id, op_ing1_user = setup_operator(factory, 'op_ing1', 'Ingeniero 1 Core', position_id=pos_ingenieria['id'], department_id=dept['id'])
    op_ing2_id, op_ing2_user = setup_operator(factory, 'op_ing2', 'Ingeniero 2 Core', position_id=pos_ingenieria['id'], department_id=dept['id'])
    op_n2_id, op_n2_user = setup_operator(factory, 'op_n2_user', 'Operador N2', position_id=pos_n2['id'], department_id=dept['id'])

    # Create customer ticket assigned to Soporte operator
    payload = {**ticket_payload, 'responsible_id': op_soporte_id, 'title': 'Falla de cliente'}
    ticket1_id = client.post('/api/tickets', json=payload).json()['id']
    esc_reason = client.post('/api/escalation-reasons', json={'name': 'N2 requerido'}).json()

    # Create internal ticket assigned to Soporte operator
    int_inc = client.post('/api/internal-incident-types', json={'name': 'Core BGP'}).json()
    ticket2_id = create_internal_ticket(client, ticket_payload['sector_id'], dept['id'], int_inc['id'], 'Ticket Interno Red', responsible_id=op_soporte_id)

    # 1. Escalate Ticket 1 (Customer) to op_ing1 (recipient_id = op_ing1_id)
    esc1_res = client.post(f'/api/tickets/{ticket1_id}/escalations', json={
        'reason_id': esc_reason['id'],
        'description': 'Escalando Ticket 1 a Ingeniero 1',
        'department_id': dept['id'],
        'requester_id': op_soporte_id,
        'recipient_id': op_ing1_id,
    })
    assert esc1_res.status_code == 201, esc1_res.text
    esc1_id = esc1_res.json()['id']

    # 2. Escalate Ticket 2 (Internal) to op_ing2 (recipient_id = op_ing2_id)
    esc2_res = client.post(f'/api/internal-tickets/{ticket2_id}/escalations', json={
        'reason_id': esc_reason['id'],
        'description': 'Escalando Ticket 2 a Ingeniero 2',
        'department_id': dept['id'],
        'requester_id': op_soporte_id,
        'recipient_id': op_ing2_id,
    })
    assert esc2_res.status_code == 201, esc2_res.text
    esc2_id = esc2_res.json()['id']

    # --- Rule 1 & 2: Login as op_ing1 (assigned recipient of Escalation 1) ---
    authorize(client, login(client, username=op_ing1_user))
    res1 = client.get('/api/my-tickets?view=escalations&escalation_status=ACTIVE')
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1['total'] == 1
    item1 = data1['items'][0]
    assert item1['id'] == ticket1_id
    assert item1['escalation_id'] == esc1_id
    assert item1['ticket_type'] == 'CUSTOMER'
    assert item1['escalation_status'] == 'ACTIVE'
    assert item1['escalation_recipient_name'] == 'Ingeniero 1 Core'
    assert item1['escalation_requester_name'] == 'Operador Soporte'
    # Rule 9: Ticket responsible is Soporte, but escalation responsible is op_ing1 -> SÍ aparece
    assert item1['responsible_id'] == op_soporte_id
    assert item1['responsible_name'] == 'Operador Soporte'
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 1

    # --- Rule 7: Login as op_ing2 (same position as op_ing1, but assigned Escalation 2) ---
    authorize(client, login(client, username=op_ing2_user))
    res2 = client.get('/api/my-tickets?view=escalations&escalation_status=ACTIVE')
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2['total'] == 1
    item2 = data2['items'][0]
    assert item2['id'] == ticket2_id
    assert item2['escalation_id'] == esc2_id
    assert item2['ticket_type'] == 'INTERNAL'
    assert item2['escalation_recipient_name'] == 'Ingeniero 2 Core'
    # op_ing2 does NOT see Ticket 1 assigned to op_ing1
    assert all(it['id'] != ticket1_id for it in data2['items'])
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 1

    # --- Rule 8: Login as op_soporte (requested both escalations, but assigned to neither) ---
    authorize(client, login(client, username=op_soporte_user))
    res_sop = client.get('/api/my-tickets?view=escalations')
    assert res_sop.json()['total'] == 0
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 0

    # --- Login as op_n2 (another position, no escalations assigned) ---
    authorize(client, login(client, username=op_n2_user))
    res_n2 = client.get('/api/my-tickets?view=escalations')
    assert res_n2.json()['total'] == 0
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 0

    # --- Rule 13: Multiple escalations on the same ticket preserved without arbitrary discarding ---
    authorize(client, login(client))  # Superadmin
    esc3_res = client.post(f'/api/tickets/{ticket1_id}/escalations', json={
        'reason_id': esc_reason['id'],
        'description': 'Segundo escalamiento en Ticket 1 para Ingeniero 1',
        'department_id': dept['id'],
        'requester_id': op_soporte_id,
        'recipient_id': op_ing1_id,
    })
    assert esc3_res.status_code == 201
    esc3_id = esc3_res.json()['id']

    authorize(client, login(client, username=op_ing1_user))
    res_multi = client.get('/api/my-tickets?view=escalations&escalation_status=ACTIVE')
    assert res_multi.json()['total'] == 2
    esc_ids = {it['escalation_id'] for it in res_multi.json()['items']}
    assert esc_ids == {esc1_id, esc3_id}
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 2

    # --- Rule 3 & 11: Finish escalation 1 and verify ACTIVE vs FINISHED vs ALL filters ---
    now_iso = datetime.now(timezone.utc).isoformat()
    client.post(f'/api/tickets/{ticket1_id}/escalations/{esc1_id}/finish', json={'finished_at': now_iso})

    res_active = client.get('/api/my-tickets?view=escalations&escalation_status=ACTIVE')
    assert res_active.json()['total'] == 1
    assert res_active.json()['items'][0]['escalation_id'] == esc3_id
    assert client.get('/api/my-tickets/summary').json()['escalations_count'] == 1

    res_finished = client.get('/api/my-tickets?view=escalations&escalation_status=FINISHED')
    assert res_finished.json()['total'] == 1
    assert res_finished.json()['items'][0]['escalation_id'] == esc1_id

    res_all = client.get('/api/my-tickets?view=escalations&escalation_status=ALL')
    assert res_all.json()['total'] == 2


def test_my_tickets_to_verify_and_ack_integration(security_client, ticket_payload):
    client, app, factory = security_client

    make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    dept = client.post('/api/departments', json={'name': 'NOC'}).json()
    pos_soporte = client.post('/api/positions', json={'name': 'Soporte', 'department_id': dept['id']}).json()
    pos_supervisor = client.post('/api/positions', json={'name': 'Supervisor', 'department_id': dept['id']}).json()

    # Soporte scales to Supervisor after 20 minutes
    client.patch(f"/api/positions/{pos_soporte['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 20,
        'destinations': [{'target_position_id': pos_supervisor['id']}],
    })

    op_soporte_id, op_soporte_user = setup_operator(factory, 'op_sop_tv', 'Op Soporte', position_id=pos_soporte['id'], department_id=dept['id'])
    op_super_id, op_super_user = setup_operator(factory, 'op_sup_tv', 'Op Supervisor', position_id=pos_supervisor['id'], department_id=dept['id'])

    # Create ticket opened 25 minutes ago
    t_25m_ago = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
    payload = {
        **ticket_payload,
        'responsible_id': op_soporte_id,
        'title': 'Ticket con umbral superado',
        'start_at': t_25m_ago,
    }
    ticket_id = client.post('/api/tickets', json=payload).json()['id']

    # Update ticket created_at in db so stage timer reflects 25 minutes
    with factory() as session:
        t = session.get(Ticket, ticket_id)
        t.created_at = datetime.now(timezone.utc) - timedelta(minutes=25)
        session.commit()

    # Login as Supervisor operator
    authorize(client, login(client, username=op_super_user))

    # 1. Ticket appears in 'Por verificar' for Supervisor!
    res = client.get('/api/my-tickets?view=to_verify')
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['total'] == 1
    item = data['items'][0]
    assert item['id'] == ticket_id
    assert item['has_recommendation'] is True
    assert item['recommendation_target_position_name'] == 'Supervisor'
    assert item['recommendation_threshold_minutes'] == 20
    assert item['recommendation_elapsed_minutes'] >= 25
    assert item['recommendation_overdue_minutes'] >= 5

    # 2. Summary count reflects 1 ticket in to_verify
    res_summary = client.get('/api/my-tickets/summary')
    assert res_summary.status_code == 200
    assert res_summary.json()['to_verify_count'] == 1

    # 3. Create active ACK on the ticket -> silences recommendation and disappears from 'Por verificar'
    ack_res = client.post(f'/api/tickets/{ticket_id}/ack', json={
        'duration_type': '1H',
        'reason': 'Validando con cliente',
    })
    assert ack_res.status_code == 201, ack_res.text

    res_silenced = client.get('/api/my-tickets?view=to_verify')
    assert res_silenced.json()['total'] == 0
    assert client.get('/api/my-tickets/summary').json()['to_verify_count'] == 0

    # 4. Revoke ACK -> ticket immediately re-appears in 'Por verificar'
    client.post(f'/api/tickets/{ticket_id}/ack/revoke', json={'reason': 'Retiro de prueba'})

    res_reappeared = client.get('/api/my-tickets?view=to_verify')
    assert res_reappeared.json()['total'] == 1
    assert client.get('/api/my-tickets/summary').json()['to_verify_count'] == 1

    # 5. Close ticket -> closed ticket never appears in 'Por verificar'
    authorize(client, login(client))  # admin
    client.patch(f'/api/tickets/{ticket_id}', json={'status': 'CLOSED'})

    authorize(client, login(client, username=op_super_user))
    res_closed = client.get('/api/my-tickets?view=to_verify')
    assert res_closed.json()['total'] == 0
