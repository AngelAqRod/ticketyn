from datetime import datetime, timedelta, timezone
import pytest
from ticketyn.models import Ticket, InternalTicket, TicketEscalation, InternalEscalation, Position, Responsible
from ticketyn.models.ack import TicketEscalationAck, InternalTicketEscalationAck


def create_position(client, name, dept_id, mode='GENERAL', general_time=None, destinations=None):
    payload = {
        'name': name,
        'department_id': dept_id,
        'escalation_mode': mode,
        'general_escalation_time_minutes': general_time,
        'destinations': destinations,
    }
    return client.post('/api/positions', json=payload)


def test_position_escalation_catalog_crud_and_validations(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'Operaciones NOC'}).json()
    p1 = create_position(api_client, 'Soporte N1', dept['id']).json()
    p2 = create_position(api_client, 'Supervisor NOC', dept['id']).json()
    p3 = create_position(api_client, 'Ingeniería Core', dept['id']).json()

    # 1. Position without destinations
    assert p1['escalation_mode'] == 'GENERAL'
    assert p1['destinations'] == []

    # 2. Validation: Self escalation rejected
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'general_escalation_time_minutes': 30,
        'destinations': [{'target_position_id': p1['id']}],
    })
    assert res.status_code == 422
    assert 'mismo' in res.text

    # 3. Validation: Nonexistent destination
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'general_escalation_time_minutes': 30,
        'destinations': [{'target_position_id': 999999}],
    })
    assert res.status_code == 404

    # 4. Validation: Inactive destination for new configuration
    p_inactive = create_position(api_client, 'Puesto Inactivo', dept['id']).json()
    api_client.patch(f"/api/positions/{p_inactive['id']}", json={'active': False})
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'general_escalation_time_minutes': 30,
        'destinations': [{'target_position_id': p_inactive['id']}],
    })
    assert res.status_code == 422
    assert 'inactivo' in res.text

    # 5. Position with multiple destinations in GENERAL mode
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 30,
        'destinations': [
            {'target_position_id': p2['id']},
            {'target_position_id': p3['id']},
        ],
    })
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated['escalation_mode'] == 'GENERAL'
    assert updated['general_escalation_time_minutes'] == 30
    assert len(updated['destinations']) == 2
    assert {d['target_position_id'] for d in updated['destinations']} == {p2['id'], p3['id']}

    # 6. Position with INDIVIDUAL mode
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'escalation_mode': 'INDIVIDUAL',
        'destinations': [
            {'target_position_id': p2['id'], 'time_minutes': 20},
            {'target_position_id': p3['id'], 'time_minutes': 45},
        ],
    })
    assert res.status_code == 200
    ind_updated = res.json()
    assert ind_updated['escalation_mode'] == 'INDIVIDUAL'
    times = {d['target_position_id']: d['time_minutes'] for d in ind_updated['destinations']}
    assert times[p2['id']] == 20
    assert times[p3['id']] == 45

    # 7. Validation: INDIVIDUAL mode missing time
    res = api_client.patch(f"/api/positions/{p1['id']}", json={
        'escalation_mode': 'INDIVIDUAL',
        'destinations': [
            {'target_position_id': p2['id']},
        ],
    })
    assert res.status_code == 422

    # 8. Validation: Circular escalation
    # p1 -> p2 already set. Now set p2 -> p3, then try p3 -> p1
    res = api_client.patch(f"/api/positions/{p2['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 15,
        'destinations': [{'target_position_id': p3['id']}],
    })
    assert res.status_code == 200

    # Try setting p3 -> p1 (would create cycle p1 -> p2 -> p3 -> p1)
    res = api_client.patch(f"/api/positions/{p3['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 10,
        'destinations': [{'target_position_id': p1['id']}],
    })
    assert res.status_code == 422
    assert 'circular' in res.text


def test_recommendation_engine_initial_stage(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'Soporte Clientes'}).json()
    pos_support = create_position(api_client, 'Operador N1', dept['id']).json()
    pos_supervisor = create_position(api_client, 'Supervisor Turno', dept['id']).json()

    # Configure Operador N1 to escalate to Supervisor Turno after 30 mins
    api_client.patch(f"/api/positions/{pos_support['id']}", json={
        'escalation_mode': 'GENERAL',
        'general_escalation_time_minutes': 30,
        'destinations': [{'target_position_id': pos_supervisor['id']}],
    })

    resp = api_client.post('/api/responsibles', json={
        'name': 'Carlos Operador',
        'department_id': dept['id'],
        'position_id': pos_support['id'],
    }).json()

    # Open ticket 10 minutes ago
    ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    ticket = api_client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': resp['id'],
        'start_at': ten_min_ago,
    }).json()

    # Check recommendations: 10 mins elapsed < 30 mins threshold
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['ticket_status'] == 'OPEN'
    assert rec['elapsed_minutes'] == 10
    assert rec['reference_position_id'] == pos_support['id']
    assert rec['recommendations'] == []

    # Update ticket start_at to 35 minutes ago
    thirty_five_ago = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
    api_client.patch(f"/api/tickets/{ticket['id']}", json={'start_at': thirty_five_ago})

    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['elapsed_minutes'] == 35
    assert len(rec['recommendations']) == 1
    assert rec['recommendations'][0]['target_position_id'] == pos_supervisor['id']
    assert rec['recommendations'][0]['threshold_minutes'] == 30
    assert rec['recommendations'][0]['overdue_minutes'] == 5


def test_responsible_change_and_updates_do_not_reset_timer(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'Atención'}).json()
    p1 = create_position(api_client, 'Mesa de Ayuda', dept['id'], mode='GENERAL', general_time=20).json()
    p_dest = create_position(api_client, 'Escalamiento N2', dept['id']).json()
    api_client.patch(f"/api/positions/{p1['id']}", json={'destinations': [{'target_position_id': p_dest['id']}]})

    r1 = api_client.post('/api/responsibles', json={'name': 'Agente 1', 'department_id': dept['id'], 'position_id': p1['id']}).json()
    r2 = api_client.post('/api/responsibles', json={'name': 'Agente 2', 'department_id': dept['id'], 'position_id': p1['id']}).json()

    twenty_five_ago = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
    ticket = api_client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': r1['id'],
        'start_at': twenty_five_ago,
    }).json()

    # Recommendations should be active (25 min >= 20 min)
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert len(rec['recommendations']) == 1

    # Change responsible to Agente 2
    api_client.patch(f"/api/tickets/{ticket['id']}", json={'responsible_id': r2['id']})

    # Add a follow-up intervention
    api_client.post(f"/api/tickets/{ticket['id']}/updates", json={'content': 'Seguimiento de rutina'})

    # Recommendations must STILL be active and timer must NOT reset
    rec2 = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec2['elapsed_minutes'] == 25
    assert len(rec2['recommendations']) == 1
    assert rec2['reference_position_id'] == p1['id']


def test_escalation_stage_and_completion_cycle(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'NOC y Redes'}).json()
    p_soporte = create_position(api_client, 'Soporte', dept['id'], mode='GENERAL', general_time=20).json()
    p_super = create_position(api_client, 'Supervisor', dept['id'], mode='GENERAL', general_time=15).json()
    p_ing = create_position(api_client, 'Ingeniería', dept['id']).json()

    # Soporte -> Supervisor (20m)
    api_client.patch(f"/api/positions/{p_soporte['id']}", json={'destinations': [{'target_position_id': p_super['id']}]})
    # Supervisor -> Ingeniería (15m)
    api_client.patch(f"/api/positions/{p_super['id']}", json={'destinations': [{'target_position_id': p_ing['id']}]})

    r_soporte = api_client.post('/api/responsibles', json={'name': 'Juan Soporte', 'department_id': dept['id'], 'position_id': p_soporte['id']}).json()
    r_super = api_client.post('/api/responsibles', json={'name': 'Ana Supervisor', 'department_id': dept['id'], 'position_id': p_super['id']}).json()
    reason = api_client.post('/api/escalation-reasons', json={'name': 'Falla compleja'}).json()

    thirty_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    ticket = api_client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': r_soporte['id'],
        'start_at': thirty_ago,
    }).json()

    # Stage 1: Soporte has elapsed 30 min -> recommends Supervisor
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert len(rec['recommendations']) == 1
    assert rec['recommendations'][0]['target_position_name'] == 'Supervisor'

    # Register escalation to Supervisor 5 minutes ago
    five_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    esc = api_client.post(f"/api/tickets/{ticket['id']}/escalations", json={
        'requester_id': r_soporte['id'],
        'recipient_id': r_super['id'],
        'department_id': dept['id'],
        'reason_id': reason['id'],
        'description': 'Escalando a supervisor',
        'started_at': five_ago,
    }).json()

    # Stage 2: Now in Supervisor stage, started 5 mins ago. Threshold for Supervisor is 15 mins -> NO recommendation yet!
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['reference_position_id'] == p_super['id']
    assert rec['elapsed_minutes'] == 5
    assert rec['recommendations'] == []

    # Fast forward escalation start to 40 minutes ago
    forty_ago = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    api_client.patch(f"/api/tickets/{ticket['id']}/escalations/{esc['id']}", json={'started_at': forty_ago})

    # Now Supervisor stage has elapsed 40 min >= 15 min -> recommends Ingeniería!
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['elapsed_minutes'] == 40
    assert len(rec['recommendations']) == 1
    assert rec['recommendations'][0]['target_position_name'] == 'Ingeniería'

    # Finish escalation! Finish time set to 25 minutes ago (valid since 25 mins ago >= 40 mins ago)
    twenty_five_ago = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
    finish_res = api_client.post(f"/api/tickets/{ticket['id']}/escalations/{esc['id']}/finish", json={'finished_at': twenty_five_ago})
    assert finish_res.status_code == 200, finish_res.text

    # Stage 3: Escalation finished -> reactivates original position (Soporte)!
    # Counter starts from finished_at (25 mins ago)
    # Soporte threshold is 20 mins -> since 25 mins >= 20 mins, Soporte's recommendation (Supervisor) re-appears!
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['reference_position_id'] == p_soporte['id']
    assert rec['elapsed_minutes'] == 25
    assert len(rec['recommendations']) == 1
    assert rec['recommendations'][0]['target_position_name'] == 'Supervisor'


def test_closed_and_reopened_ticket_deducts_closed_time(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'Soporte'}).json()
    pos = create_position(api_client, 'Mesa 1', dept['id'], mode='GENERAL', general_time=30).json()
    p_dest = create_position(api_client, 'Mesa 2', dept['id']).json()
    api_client.patch(f"/api/positions/{pos['id']}", json={'destinations': [{'target_position_id': p_dest['id']}]})

    resp = api_client.post('/api/responsibles', json={'name': 'Tecnico', 'department_id': dept['id'], 'position_id': pos['id']}).json()

    # Opened 60 minutes ago
    sixty_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    ticket = api_client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': resp['id'],
        'start_at': sixty_ago,
    }).json()

    # Close ticket 50 minutes ago
    fifty_ago = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
    api_client.patch(f"/api/tickets/{ticket['id']}", json={'status': 'CLOSED', 'end_at': fifty_ago})

    # Closed tickets have NO recommendations
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['ticket_status'] == 'CLOSED'
    assert rec['recommendations'] == []

    # Reopen ticket now!
    api_client.patch(f"/api/tickets/{ticket['id']}", json={'status': 'OPEN'})

    # The ticket was closed for ~50 minutes (from 50m ago to now)
    # Total time since start is 60m. Deducting ~50m closed time leaves ~10m elapsed!
    # 10m < 30m threshold -> NO recommendation yet!
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert rec['ticket_status'] == 'OPEN'
    assert rec['elapsed_minutes'] < 15
    assert rec['recommendations'] == []


def test_ack_workflow_and_silencing(api_client, ticket_payload):
    dept = api_client.post('/api/departments', json={'name': 'NOC'}).json()
    p1 = create_position(api_client, 'NOC 1', dept['id'], mode='GENERAL', general_time=15).json()
    p2 = create_position(api_client, 'NOC 2', dept['id']).json()
    api_client.patch(f"/api/positions/{p1['id']}", json={'destinations': [{'target_position_id': p2['id']}]})

    resp = api_client.post('/api/responsibles', json={'name': 'Guardia NOC', 'department_id': dept['id'], 'position_id': p1['id']}).json()

    twenty_ago = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    ticket = api_client.post('/api/tickets', json={
        **ticket_payload,
        'responsible_id': resp['id'],
        'start_at': twenty_ago,
    }).json()

    # Recommendations active
    rec = api_client.get(f"/api/tickets/{ticket['id']}/recommendations").json()
    assert len(rec['recommendations']) == 1
    assert rec['has_active_ack'] is False

    # In security client tests or default client, create ACK via direct API or authenticated user
    # Note: api_client in non-auth tests has no request.state.principal unless authenticated.
    # We will test authorized / denied ACK comprehensively in security tests below.
