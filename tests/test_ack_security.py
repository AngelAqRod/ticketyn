from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from ticketyn.models import Department, Position, PositionEscalationDestination, Responsible, SecurityRole, Ticket
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


def test_ack_lifecycle_authorization_and_silencing(security_client, ticket_payload):
    client, app, factory = security_client

    # 1. Create Superadmin account and login
    admin_id = make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    # Setup department and positions
    dept = client.post('/api/departments', json={'name': 'Operaciones'}).json()
    pos_soporte = client.post('/api/positions', json={'name': 'Soporte', 'department_id': dept['id']}).json()
    pos_supervisor = client.post('/api/positions', json={'name': 'Supervisor', 'department_id': dept['id']}).json()
    pos_otro = client.post('/api/positions', json={'name': 'Finanzas', 'department_id': dept['id']}).json()

    # Soporte scales to Supervisor after 20 minutes
    client.patch(f"/api/positions/{pos_soporte['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 20,
        'destinations': [{'target_position_id': pos_supervisor['id']}],
    })

    # Create operators in different positions
    op_soporte_id, op_soporte_user = setup_operator(factory, 'op_soporte', 'Operador Soporte', position_id=pos_soporte['id'], department_id=dept['id'])
    op_super_id, op_super_user = setup_operator(factory, 'op_super', 'Operador Supervisor', position_id=pos_supervisor['id'], department_id=dept['id'])
    op_otro_id, op_otro_user = setup_operator(factory, 'op_otro', 'Operador Finanzas', position_id=pos_otro['id'], department_id=dept['id'])
    auditor_id, auditor_user = setup_operator(factory, 'auditor_user', 'Auditor', role_code='AUDITOR', position_id=pos_soporte['id'], department_id=dept['id'])

    # Open ticket 30 minutes ago assigned to Soporte
    thirty_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    ticket = client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': op_soporte_id,
        'start_at': thirty_ago,
    }).json()

    # Check recommendations active (30m >= 20m)
    rec = client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert len(rec['recommendations']) == 1
    assert rec['has_active_ack'] is False

    # 2. Authorization checks:
    # A) Auditor tries to ACK -> 403 (Auditor lacks tickets.escalate)
    authorize(client, login(client, username=auditor_user))
    res = client.post(f"/api/tickets/{ticket['id']}/ack", json={'duration_type': '1H', 'reason': 'Intento auditor'})
    assert res.status_code == 403

    # B) Operator in unrelated position (Finanzas) tries to ACK -> 403 (Not in escalation flow)
    authorize(client, login(client, username=op_otro_user))
    res = client.post(f"/api/tickets/{ticket['id']}/ack", json={'duration_type': '1H', 'reason': 'Intento finanzas'})
    assert res.status_code == 403
    assert 'no está habilitado' in res.text

    # C) Operator in Soporte (stage reference position) CAN ACK!
    authorize(client, login(client, username=op_soporte_user))
    res = client.post(f"/api/tickets/{ticket['id']}/ack", json={'duration_type': '4H', 'reason': 'Investigando con proveedor local'})
    assert res.status_code == 201, res.text
    ack = res.json()
    assert ack['duration_type'] == '4H'
    assert ack['active'] is True
    assert ack['acknowledged_by']['id'] == op_soporte_id
    assert ack['expires_at'] is not None

    # 3. Duplicate ACK check
    res_dup = client.post(f"/api/tickets/{ticket['id']}/ack", json={'duration_type': '1H', 'reason': 'Segundo ack'})
    assert res_dup.status_code == 409
    assert 'vigente' in res_dup.text

    # 4. Silencing verification: recommendations must now be EMPTY while ACK is active
    rec = client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['has_active_ack'] is True
    assert rec['active_ack'] is not None
    assert rec['recommendations'] == []

    # 5. Revocation by operator in Supervisor position (destination in flow)
    authorize(client, login(client, username=op_super_user))
    rev_res = client.post(f"/api/tickets/{ticket['id']}/ack/revoke", json={'reason': 'Retirado por supervisor para escalar'})
    assert rev_res.status_code == 200
    assert rev_res.json()['active'] is False

    # Recommendations must immediately RE-APPEAR after revocation!
    rec = client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['has_active_ack'] is False
    assert len(rec['recommendations']) == 1

    # 6. Indefinite ACK by Admin
    authorize(client, login(client))
    res_indef = client.post(f"/api/tickets/{ticket['id']}/ack", json={'duration_type': 'INDEFINITE', 'reason': 'Falla masiva programada'})
    assert res_indef.status_code == 201
    ack_indef = res_indef.json()
    assert ack_indef['duration_type'] == 'INDEFINITE'
    assert ack_indef['expires_at'] is None

    # Recommendations silenced
    rec = client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['has_active_ack'] is True
    assert rec['recommendations'] == []

    # 7. Closing ticket concludes active ACK
    client.patch(f"/api/tickets/{ticket['id']}", json={'status': 'CLOSED'})

    # Query ACK history: verify all ACKs preserved in historical order
    acks = client.get(f"/api/tickets/{ticket['id']}/acks").json()
    assert len(acks) == 2
    assert all(a['active'] is False for a in acks)


def test_internal_ticket_ack_and_recommendations(security_client):
    client, app, factory = security_client
    make_account(factory, role='SUPERADMIN')
    authorize(client, login(client))

    dept = client.post('/api/departments', json={'name': 'Infraestructura'}).json()
    p_n1 = client.post('/api/positions', json={
        'name': 'Redes N1',
        'department_id': dept['id'],
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 15,
    }).json()
    p_n2 = client.post('/api/positions', json={'name': 'Redes Core', 'department_id': dept['id']}).json()
    client.patch(f"/api/positions/{p_n1['id']}", json={'destinations': [{'target_position_id': p_n2['id']}]})

    resp = client.post('/api/responsibles', json={'name': 'Admin Redes', 'department_id': dept['id'], 'position_id': p_n1['id']}).json()
    kind = client.post('/api/internal-incident-types', json={'name': 'Corte de fibra'}).json()
    sec = client.post('/api/sectors', json={'name': 'Sector Troncal'}).json()

    twenty_ago = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    internal = client.post('/api/internal-tickets', json={
        'title': 'Corte en anillo norte',
        'description': 'Alarma de fibra cortada',
        'department_id': dept['id'],
        'incident_type_id': kind['id'],
        'sector_id': sec['id'],
        'responsible_id': resp['id'],
        'start_at': twenty_ago,
    }).json()

    # Recommendations should suggest Redes Core
    rec = client.get(f"/api/internal-tickets/{internal['id']}/recommendations").json()
    assert len(rec['recommendations']) == 1
    assert rec['recommendations'][0]['target_position_name'] == 'Redes Core'

    # Create ACK on internal ticket
    ack_res = client.post(f"/api/internal-tickets/{internal['id']}/ack", json={'duration_type': '1H', 'reason': 'Cuadrilla en camino'}).json()
    assert ack_res['active'] is True

    # Recommendations silenced
    rec2 = client.get(f"/api/internal-tickets/{internal['id']}/recommendations").json()
    assert rec2['has_active_ack'] is True
    assert rec2['recommendations'] == []
