import pytest


def test_ticket_stats_empty(api_client):
    response = api_client.get("/api/tickets/stats")
    assert response.status_code == 200
    assert response.json() == {"total": 0, "open": 0, "closed": 0}


@pytest.mark.parametrize("open_count,closed_count", [(2, 3), (30, 35)])
def test_ticket_stats_count_all_tickets(api_client, ticket_payload, open_count, closed_count):
    for status, count in (("OPEN", open_count), ("CLOSED", closed_count)):
        for _ in range(count):
            response = api_client.post("/api/tickets", json={**ticket_payload, "status": status})
            assert response.status_code == 201
    response = api_client.get("/api/tickets/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total": open_count + closed_count, "open": open_count, "closed": closed_count,
    }
    assert len(api_client.get("/api/tickets").json()) == min(open_count + closed_count, 50)
