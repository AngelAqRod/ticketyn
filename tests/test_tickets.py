from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ticketyn.models import Ticket, TicketNumberConfig

CONFIG_PATH = "/api/settings/ticket-number"
RELATED_PATHS = {
    "customer_id": "/api/customers", "circuit_id": "/api/circuits",
    "sector_id": "/api/sectors", "department_id": "/api/departments",
    "incident_type_id": "/api/incident-types",
}


def create_ticket(client, payload):
    response = client.post("/api/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_generic_config_initialization(api_client, db_session):
    assert db_session.get(TicketNumberConfig, 1) is None
    response = api_client.get(CONFIG_PATH)
    assert response.status_code == 200
    assert response.json() == {"id": 1, "prefix": "", "separator": "", "next_number": 1, "padding": 0}
    assert api_client.get(CONFIG_PATH).json() == response.json()
    assert len(list(db_session.scalars(select(TicketNumberConfig)))) == 1


@pytest.mark.parametrize("field,value", [("prefix", "TKD"), ("separator", "----"), ("padding", 3), ("next_number", 3)])
def test_patch_number_config(api_client, field, value):
    response = api_client.patch(CONFIG_PATH, json={field: value})
    assert response.status_code == 200
    expected = {"id": 1, "prefix": "", "separator": "", "next_number": 1, "padding": 0, field: value}
    assert response.json() == expected
    assert api_client.get(CONFIG_PATH).json() == expected


@pytest.mark.parametrize("changes", [
    {"next_number": 0}, {"next_number": -1}, {"next_number": None},
    {"next_number": 1.5}, {"next_number": True}, {"padding": -1}, {"padding": None},
    {"padding": 1.5}, {"prefix": None}, {"separator": None}, {"id": 2},
])
def test_invalid_number_config(api_client, changes):
    assert api_client.patch(CONFIG_PATH, json=changes).status_code == 422


@pytest.mark.parametrize("padding", [0, 20])
def test_padding_boundaries_and_ticket_creation(api_client, ticket_payload, padding):
    response = api_client.patch(CONFIG_PATH, json={
        "prefix": "TEST", "separator": "-", "next_number": 1, "padding": padding,
    })
    assert response.status_code == 200
    assert response.json()["padding"] == padding
    ticket = create_ticket(api_client, ticket_payload)
    assert ticket["reference"] == "TEST-" + "1".zfill(padding)
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 2


@pytest.mark.parametrize("padding", [-1, 21, 2147483647])
def test_invalid_padding_never_reaches_reference_logic(api_client, monkeypatch, padding):
    from ticketyn.api import settings

    before = api_client.get(CONFIG_PATH).json()

    def unexpected_call(*args, **kwargs):
        pytest.fail("Padding inválido llegó a la lógica de numeración")

    with monkeypatch.context() as patches:
        patches.setattr(settings, "locked_number_config", unexpected_call)
        patches.setattr(settings, "validate_number_config", unexpected_call)
        response = api_client.patch(CONFIG_PATH, json={"prefix": "NO-CHANGE", "padding": padding})
    assert response.status_code == 422
    assert any(error["loc"] == ["body", "padding"] for error in response.json()["detail"])
    assert api_client.get(CONFIG_PATH).json() == before


def test_normal_number_config_patch_and_creation(api_client, ticket_payload):
    response = api_client.patch(CONFIG_PATH, json={
        "prefix": "TEST", "separator": "-", "next_number": 1, "padding": 3,
    })
    assert response.status_code == 200
    assert create_ticket(api_client, ticket_payload)["reference"] == "TEST-001"
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 2


def test_padding_openapi_constraints_and_example(api_client):
    schemas = api_client.get("/openapi.json").json()["components"]["schemas"]
    padding = schemas["TicketNumberConfigUpdate"]["properties"]["padding"]
    integer_schema = next(option for option in padding["anyOf"] if option["type"] == "integer")
    assert integer_schema["minimum"] == 0
    assert integer_schema["maximum"] == 20
    assert padding["examples"] == [3]


@pytest.mark.parametrize("config,references", [
    ({}, ["1", "2"]),
    ({"prefix": "TKD", "separator": "-", "next_number": 3, "padding": 3}, ["TKD-003", "TKD-004"]),
    ({"prefix": "THK", "separator": "----", "padding": 3}, ["THK----001", "THK----002"]),
    ({"padding": 1, "next_number": 100}, ["100", "101"]),
])
def test_number_generation_and_increment(api_client, ticket_payload, config, references):
    assert api_client.patch(CONFIG_PATH, json=config).status_code == 200
    first = create_ticket(api_client, ticket_payload)
    second = create_ticket(api_client, ticket_payload)
    assert [first["reference"], second["reference"]] == references
    assert second["ticket_number"] == first["ticket_number"] + 1
    assert api_client.get(CONFIG_PATH).json()["next_number"] == second["ticket_number"] + 1


def test_references_remain_stored_after_config_change(api_client, ticket_payload):
    assert api_client.patch(CONFIG_PATH, json={"prefix": "ABC", "separator": "-", "padding": 3}).status_code == 200
    first = create_ticket(api_client, ticket_payload)
    assert first["reference"] == "ABC-001"
    assert api_client.patch(CONFIG_PATH, json={"prefix": "TKD", "padding": 4}).status_code == 200
    assert api_client.get(f"/api/tickets/{first['id']}").json()["reference"] == "ABC-001"
    assert create_ticket(api_client, ticket_payload)["reference"] == "TKD-0002"


def test_config_rejects_reused_numbers(api_client, ticket_payload):
    create_ticket(api_client, ticket_payload)
    response = api_client.patch(CONFIG_PATH, json={"prefix": "NEW", "next_number": 1})
    assert response.status_code == 409
    assert api_client.get(CONFIG_PATH).json()["prefix"] == ""
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 2
    assert api_client.patch(CONFIG_PATH, json={"next_number": 10}).status_code == 200
    assert create_ticket(api_client, ticket_payload)["ticket_number"] == 10


def test_config_rejects_proposed_reference_collision(api_client, ticket_payload):
    assert api_client.patch(CONFIG_PATH, json={"prefix": "A2", "next_number": 1}).status_code == 200
    first = create_ticket(api_client, ticket_payload)
    assert first["reference"] == "A21"
    response = api_client.patch(CONFIG_PATH, json={"prefix": "A", "next_number": 21})
    assert response.status_code == 409
    assert api_client.get(CONFIG_PATH).json()["prefix"] == "A2"


@pytest.mark.parametrize("status", ["OPEN", "CLOSED"])
@pytest.mark.parametrize("end_at", [None, "2020-01-01T13:30:00Z"])
def test_create_all_status_and_end_combinations(api_client, ticket_payload, status, end_at):
    item = create_ticket(api_client, {**ticket_payload, "status": status, "end_at": end_at})
    assert item["status"] == status
    assert item["duration_seconds"] == (5400 if end_at else None)
    assert item["ticket_number"] == 1
    assert item["reference"] == "1"
    assert datetime.fromisoformat(item["start_at"]).year == 2020
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(item["updated_at"]).tzinfo is not None
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item
    assert "active" not in item


def test_default_status_open(api_client, ticket_payload):
    payload = ticket_payload.copy()
    payload.pop("status")
    assert create_ticket(api_client, payload)["status"] == "OPEN"


def test_equal_dates_and_timezone_offsets(api_client, ticket_payload):
    item = create_ticket(api_client, {**ticket_payload, "end_at": "2020-01-01T06:00:00-06:00"})
    assert item["duration_seconds"] == 0
    assert api_client.post("/api/tickets", json={**ticket_payload, "end_at": "2020-01-01T06:00:00+00:00"}).status_code == 422


def test_invalid_dates_do_not_consume_number(api_client, ticket_payload):
    assert api_client.post("/api/tickets", json={**ticket_payload, "end_at": "2019-12-31T23:00:00Z"}).status_code == 422
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 1
    assert create_ticket(api_client, ticket_payload)["ticket_number"] == 1


@pytest.mark.parametrize("field", list(RELATED_PATHS))
def test_nonexistent_relation(api_client, ticket_payload, field):
    response = api_client.post("/api/tickets", json={**ticket_payload, field: 999999})
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 1
    item = create_ticket(api_client, ticket_payload)
    response = api_client.patch(f"/api/tickets/{item['id']}", json={field: 999999})
    assert response.status_code == 404
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item


@pytest.mark.parametrize("field", list(RELATED_PATHS))
def test_inactive_create_and_historical_edit(api_client, ticket_payload, field):
    item = create_ticket(api_client, ticket_payload)
    assert api_client.patch(f"{RELATED_PATHS[field]}/{ticket_payload[field]}", json={"active": False}).status_code == 200
    response = api_client.post("/api/tickets", json=ticket_payload)
    assert response.status_code == 422
    assert "inactivo" in response.json()["detail"]
    assert api_client.get(CONFIG_PATH).json()["next_number"] == 2
    assert api_client.get(f"/api/tickets/{item['id']}").status_code == 200
    response = api_client.patch(f"/api/tickets/{item['id']}", json={"title": "Corrección histórica", "status": "CLOSED"})
    assert response.status_code == 200
    assert response.json()["title"] == "Corrección histórica"


def test_incompatible_customer_circuit(api_client, ticket_payload):
    customer = api_client.post("/api/customers", json={"customer_code": "OTHER", "name": "Otro"}).json()
    response = api_client.post("/api/tickets", json={**ticket_payload, "customer_id": customer["id"]})
    assert response.status_code == 422
    assert "no pertenece" in response.json()["detail"]
    item = create_ticket(api_client, ticket_payload)
    assert api_client.patch(f"/api/tickets/{item['id']}", json={"customer_id": customer["id"]}).status_code == 422
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item
    circuit = api_client.post("/api/circuits", json={
        "customer_id": customer["id"], "circuit_code": "NO-PREFIX-RELATION", "description": "Otro"
    }).json()
    response = api_client.patch(f"/api/tickets/{item['id']}", json={"customer_id": customer["id"], "circuit_id": circuit["id"]})
    assert response.status_code == 200
    assert response.json()["customer_id"] == customer["id"]
    assert response.json()["circuit_id"] == circuit["id"]


def test_patch_revalidates_membership_after_catalog_reassignment(api_client, ticket_payload):
    item = create_ticket(api_client, ticket_payload)
    customer = api_client.post("/api/customers", json={"customer_code": "REASSIGNED", "name": "Otro"}).json()
    assert api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={"customer_id": customer["id"]}).status_code == 200
    response = api_client.patch(f"/api/tickets/{item['id']}", json={"title": "Corrección"})
    assert response.status_code == 422
    # El histórico sigue siendo consultable y se puede corregir la relación.
    assert api_client.get(f"/api/tickets/{item['id']}").status_code == 200
    assert api_client.patch(f"/api/tickets/{item['id']}", json={"customer_id": customer["id"]}).status_code == 200


@pytest.mark.parametrize("field", list(RELATED_PATHS))
def test_reassign_to_inactive_resource_rejected(api_client, ticket_payload, field):
    item = create_ticket(api_client, ticket_payload)
    if field == "customer_id":
        body = {"customer_code": "INACTIVE", "name": "Otro cliente"}
    elif field == "circuit_id":
        body = {"customer_id": ticket_payload["customer_id"], "circuit_code": "INACTIVE", "description": "Otro enlace"}
    else:
        body = {"name": "Registro inactivo"}
    created = api_client.post(RELATED_PATHS[field], json=body)
    assert created.status_code == 201
    resource_id = created.json()["id"]
    assert api_client.patch(f"{RELATED_PATHS[field]}/{resource_id}", json={"active": False}).status_code == 200
    response = api_client.patch(f"/api/tickets/{item['id']}", json={field: resource_id})
    assert response.status_code == 422
    assert "inactivo" in response.json()["detail"]
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item


@pytest.mark.parametrize("field", ["circuit_id", "sector_id", "department_id", "incident_type_id"])
def test_reassign_to_active_resource(api_client, ticket_payload, field):
    item = create_ticket(api_client, ticket_payload)
    if field == "circuit_id":
        body = {"customer_id": ticket_payload["customer_id"], "circuit_code": "NEW", "description": "Nuevo enlace"}
    else:
        body = {"name": "Nuevo registro"}
    new = api_client.post(RELATED_PATHS[field], json=body)
    assert new.status_code == 201
    response = api_client.patch(f"/api/tickets/{item['id']}", json={field: new.json()["id"]})
    assert response.status_code == 200
    assert response.json()[field] == new.json()["id"]


@pytest.mark.parametrize("status", ["OPEN", "CLOSED"])
def test_partial_patch_and_updated_at(api_client, ticket_payload, status):
    item = create_ticket(api_client, {**ticket_payload, "status": status})
    response = api_client.patch(f"/api/tickets/{item['id']}", json={"title": "Título corregido", "description": "Corregido"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Título corregido"
    assert updated["description"] == "Corregido"
    assert datetime.fromisoformat(updated["updated_at"]) > datetime.fromisoformat(item["updated_at"])
    for field in set(item) - {"title", "description", "updated_at"}:
        assert updated[field] == item[field]


def test_date_patch_merges_current_values(api_client, ticket_payload):
    item = create_ticket(api_client, {**ticket_payload, "end_at": "2020-01-01T13:00:00Z"})
    path = f"/api/tickets/{item['id']}"
    assert api_client.patch(path, json={"start_at": "2020-01-01T14:00:00Z"}).status_code == 422
    assert api_client.patch(path, json={"end_at": "2020-01-01T11:00:00Z"}).status_code == 422
    assert api_client.get(path).json() == item
    response = api_client.patch(path, json={"start_at": "2020-01-01T13:00:00Z", "end_at": "2020-01-01T14:00:00Z", "status": "CLOSED"})
    assert response.status_code == 200
    assert response.json()["duration_seconds"] == 3600
    response = api_client.patch(path, json={"end_at": None})
    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    assert response.json()["duration_seconds"] is None
    assert api_client.patch(path, json={"status": "OPEN"}).json()["status"] == "OPEN"


@pytest.mark.parametrize("field,value", [
    ("id", 1), ("ticket_number", 123), ("reference", "MANUAL"),
    ("created_at", "2020-01-01T00:00:00Z"), ("updated_at", "2020-01-01T00:00:00Z"),
    ("duration_seconds", 1),
])
def test_immutable_fields(api_client, ticket_payload, field, value):
    assert api_client.post("/api/tickets", json={**ticket_payload, field: value}).status_code == 422
    item = create_ticket(api_client, ticket_payload)
    assert api_client.patch(f"/api/tickets/{item['id']}", json={field: value}).status_code == 422
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item


@pytest.mark.parametrize("changes", [
    {"title": ""}, {"description": "   "}, {"start_at": None}, {"customer_id": None},
    {"status": "PENDING"}, {"status": None}, {"start_at": "2020-01-01T12:00:00"},
    {"end_at": "invalid"}, {"end_at": "2020-01-01T13:00:00"}, {"sector_id": 0},
])
def test_ticket_input_validation(api_client, ticket_payload, changes):
    assert api_client.post("/api/tickets", json={**ticket_payload, **changes}).status_code == 422
    item = create_ticket(api_client, ticket_payload)
    assert api_client.patch(f"/api/tickets/{item['id']}", json=changes).status_code == 422


@pytest.mark.parametrize("field", ["title", "description", "start_at", *RELATED_PATHS])
def test_ticket_required_fields(api_client, ticket_payload, field):
    payload = ticket_payload.copy()
    payload.pop(field)
    assert api_client.post("/api/tickets", json=payload).status_code == 422


def test_ticket_not_found_and_empty_patch(api_client, ticket_payload):
    assert api_client.get("/api/tickets/999999").status_code == 404
    assert api_client.patch("/api/tickets/999999", json={}).status_code == 404
    item = create_ticket(api_client, ticket_payload)
    assert api_client.patch(f"/api/tickets/{item['id']}", json={}).json() == item


@pytest.mark.parametrize("field", ["status", *RELATED_PATHS])
def test_ticket_filters(api_client, ticket_payload, field):
    item = create_ticket(api_client, ticket_payload)
    response = api_client.get("/api/tickets", params={field: item[field]})
    assert response.status_code == 200
    assert [{key: row[key] for key in item} for row in response.json()] == [item]
    value = "CLOSED" if field == "status" else 999999
    assert api_client.get("/api/tickets", params={field: value}).json() == []
    assert api_client.get("/api/tickets", params={"status": "OPEN", "customer_id": item["customer_id"], "sector_id": 999999}).json() == []


@pytest.mark.parametrize("search", ["ref----001", "tíTuLO", "dESCRIPCIóN"])
def test_ticket_search(api_client, ticket_payload, search):
    assert api_client.patch(CONFIG_PATH, json={"prefix": "REF", "separator": "----", "padding": 3}).status_code == 200
    item = create_ticket(api_client, {**ticket_payload, "title": "Título especial", "description": "Descripción especial"})
    # Clúster C: probar case-insensitivity ASCII conservando las letras acentuadas.
    response = api_client.get("/api/tickets", params={"search": search})
    assert response.status_code == 200
    assert [{key: row[key] for key in item} for row in response.json()] == [item]
    assert api_client.get("/api/tickets", params={"search": "SIN-COINCIDENCIA"}).json() == []


def test_ticket_order_and_pagination(api_client, ticket_payload):
    first = create_ticket(api_client, ticket_payload)
    second = create_ticket(api_client, ticket_payload)
    third = create_ticket(api_client, ticket_payload)
    assert [item["id"] for item in api_client.get("/api/tickets").json()] == [third["id"], second["id"], first["id"]]
    response = api_client.get("/api/tickets", params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    assert [{key: row[key] for key in second} for row in response.json()] == [second]
    assert api_client.get("/api/tickets", params={"offset": 3}).json() == []


def test_ticket_default_limit(api_client, ticket_payload):
    items = [create_ticket(api_client, ticket_payload) for _ in range(51)]
    response = api_client.get("/api/tickets")
    assert response.status_code == 200
    assert len(response.json()) == 50
    assert response.json()[0]["id"] == items[-1]["id"]
    assert [row["id"] for row in api_client.get("/api/tickets", params={"offset": 50}).json()] == [items[0]["id"]]


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 201}, {"offset": -1}, {"limit": "invalid"},
    {"status": "UNKNOWN"}, {"customer_id": 0}, {"circuit_id": -1},
])
def test_ticket_invalid_filters(api_client, params):
    assert api_client.get("/api/tickets", params=params).status_code == 422


@pytest.mark.parametrize("unique_field", ["ticket_number", "reference"])
def test_number_conflict_rolls_back_counter(api_client, ticket_payload, db_session, unique_field):
    first = create_ticket(api_client, ticket_payload)
    config = db_session.get(TicketNumberConfig, 1)
    if unique_field == "ticket_number":
        config.next_number = first["ticket_number"]
    else:
        # El próximo número es distinto, pero la referencia calculada colisiona.
        first_ticket = db_session.get(Ticket, first["id"])
        first_ticket.reference = "2"
    db_session.commit()
    before = config.next_number
    response = api_client.post("/api/tickets", json=ticket_payload)
    assert response.status_code == 409
    assert unique_field in response.json()["detail"]
    assert "IntegrityError" not in response.text and "uq_tickets" not in response.text
    assert api_client.get(CONFIG_PATH).json()["next_number"] == before
    assert len(api_client.get("/api/tickets").json()) == 1


@pytest.mark.parametrize("field,value,constraint", [
    ("id", 2, "ck_ticket_number_config_singleton"),
    ("next_number", 0, "ck_ticket_number_config_positive_next_number"),
    ("padding", -1, "ck_ticket_number_config_nonnegative_padding"),
])
def test_config_database_constraints(db_session, field, value, constraint):
    config = TicketNumberConfig(id=1, prefix="", separator="", next_number=1, padding=0)
    setattr(config, field, value)
    db_session.add(config)
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.diag.constraint_name == constraint
