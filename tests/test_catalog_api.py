from datetime import datetime

import pytest


RESOURCES = [
    ("customers", "customer_code", {"customer_code": "SGgt-00000", "name": "Empresa ABC"}),
    ("circuits", "circuit_code", {"circuit_code": "SGgt-00000.00000", "description": "Internet principal"}),
    ("sectors", "name", {"name": "Sector Norte"}),
    ("departments", "name", {"name": "Departamento de prueba"}),
    ("incident-types", "name", {"name": "Incidencia de prueba"}),
]


@pytest.fixture(params=RESOURCES, ids=[item[0] for item in RESOURCES])
def resource(request, api_client):
    name, unique_field, original = request.param
    payload = original.copy()
    if name == "circuits":
        customer = api_client.post("/api/customers", json={
            "customer_code": "CUSTOMER-MANUAL", "name": "Cliente de circuitos"
        })
        assert customer.status_code == 201
        payload["customer_id"] = customer.json()["id"]
    return f"/api/{name}", unique_field, payload


def create(api_client, path, payload):
    response = api_client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get(api_client, resource):
    path, _, payload = resource
    item = create(api_client, path, payload)
    assert set(item) == set(payload) | {"id", "active", "created_at"}
    assert item["id"] > 0
    assert item["active"] is True
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    assert all(item[field] == value for field, value in payload.items())
    response = api_client.get(f"{path}/{item['id']}")
    assert response.status_code == 200
    assert response.json() == item


def test_list_and_order(api_client, resource):
    path, field, payload = resource
    items = [create(api_client, path, {**payload, field: value}) for value in ("C", "A", "B")]
    response = api_client.get(path)
    assert response.status_code == 200
    assert [item[field] for item in response.json()] == ["A", "B", "C"]
    assert {item["id"] for item in response.json()} == {item["id"] for item in items}


def test_partial_update(api_client, resource):
    path, field, payload = resource
    item = create(api_client, path, payload)
    changed_field = "name" if "name" in payload else "description"
    response = api_client.patch(f"{path}/{item['id']}", json={changed_field: "Texto corregido"})
    assert response.status_code == 200
    expected = {**item, changed_field: "Texto corregido"}
    assert response.json() == expected
    assert api_client.get(f"{path}/{item['id']}").json() == expected
    # El código de negocio también es editable, independientemente del ID técnico.
    response = api_client.patch(f"{path}/{item['id']}", json={field: "NUEVO-CODIGO"})
    assert response.status_code == 200
    assert response.json()[field] == "NUEVO-CODIGO"
    assert response.json()["id"] == item["id"]


def test_empty_patch_preserves_values(api_client, resource):
    path, _, payload = resource
    item = create(api_client, path, payload)
    response = api_client.patch(f"{path}/{item['id']}", json={})
    assert response.status_code == 200
    assert response.json() == item


def test_duplicate_create_rolls_back(api_client, resource):
    path, field, payload = resource
    create(api_client, path, payload)
    response = api_client.post(path, json=payload)
    assert response.status_code == 409
    assert field in response.json()["detail"]
    assert "IntegrityError" not in response.text
    assert "uq_" not in response.text
    create(api_client, path, {**payload, field: "OTRO"})
    assert len(api_client.get(path).json()) == 2


def test_duplicate_update_rolls_back(api_client, resource):
    path, field, payload = resource
    first = create(api_client, path, payload)
    second = create(api_client, path, {**payload, field: "OTRO"})
    response = api_client.patch(f"{path}/{second['id']}", json={field: first[field], "active": False})
    assert response.status_code == 409
    assert field in response.json()["detail"]
    assert api_client.get(f"{path}/{second['id']}").json() == second
    response = api_client.patch(f"{path}/{second['id']}", json={field: "TERCERO"})
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["get", "patch"])
def test_not_found(api_client, resource, method):
    path, _, _ = resource
    kwargs = {"json": {}} if method == "patch" else {}
    response = getattr(api_client, method)(f"{path}/999999", **kwargs)
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


@pytest.mark.parametrize("search_field", ["identifier", "description"])
def test_search_case_insensitive(api_client, resource, search_field):
    path, field, payload = resource
    item = create(api_client, path, payload)
    text_field = "description" if "description" in payload else "name"
    search = payload[field if search_field == "identifier" else text_field].swapcase()[1:-1]
    response = api_client.get(path, params={"search": search})
    assert response.status_code == 200
    assert response.json() == [item]
    assert api_client.get(path, params={"search": "NO-MATCH"}).json() == []


@pytest.mark.parametrize("literal", ["%", "_", "'", "/"])
def test_search_treats_special_characters_as_literals(api_client, resource, literal):
    path, field, payload = resource
    found = create(api_client, path, {**payload, field: f"VAL{literal}UE"})
    create(api_client, path, {**payload, field: "VALUE"})
    response = api_client.get(path, params={"search": literal})
    assert response.status_code == 200
    assert response.json() == [found]


def test_active_inactive_and_reactivation(api_client, resource):
    path, field, payload = resource
    active = create(api_client, path, payload)
    inactive = create(api_client, path, {**payload, field: "OTRO"})
    response = api_client.patch(f"{path}/{inactive['id']}", json={"active": False})
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert api_client.get(path).json() == [active]
    assert api_client.get(path, params={"include_inactive": False}).json() == [active]
    all_items = api_client.get(path, params={"include_inactive": True}).json()
    assert {item["id"] for item in all_items} == {active["id"], inactive["id"]}
    assert api_client.get(f"{path}/{inactive['id']}").json()["active"] is False
    assert api_client.patch(f"{path}/{inactive['id']}", json={"active": True}).status_code == 200
    assert len(api_client.get(path).json()) == 2


def test_pagination(api_client, resource):
    path, field, payload = resource
    for value in ("C", "A", "B"):
        create(api_client, path, {**payload, field: value})
    response = api_client.get(path, params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    assert [item[field] for item in response.json()] == ["B"]
    assert api_client.get(path, params={"offset": 3}).json() == []
    assert len(api_client.get(path, params={"limit": 200}).json()) == 3


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": -1}, {"limit": 201}, {"offset": -1},
    {"limit": "no-number"}, {"offset": "no-number"},
])
def test_invalid_pagination(api_client, resource, params):
    path, _, _ = resource
    assert api_client.get(path, params=params).status_code == 422


@pytest.mark.parametrize("value", [None, "", "   "])
def test_invalid_text_input(api_client, resource, value):
    path, field, payload = resource
    assert api_client.post(path, json={**payload, field: value}).status_code == 422
    item = create(api_client, path, payload)
    assert api_client.patch(f"{path}/{item['id']}", json={field: value}).status_code == 422
    assert api_client.get(f"{path}/{item['id']}").json() == item


def test_null_active_and_unknown_fields_are_rejected(api_client, resource):
    path, _, payload = resource
    item = create(api_client, path, payload)
    for patch in ({"active": None}, {"id": 123}, {"created_at": "2026-01-01"}):
        assert api_client.patch(f"{path}/{item['id']}", json=patch).status_code == 422
    assert api_client.post(path, json={**payload, "id": 123}).status_code == 422
    assert api_client.get(f"{path}/{item['id']}").json() == item


def test_default_limit(api_client):
    for number in range(51):
        create(api_client, "/api/sectors", {"name": f"Sector {number:03d}"})
    response = api_client.get("/api/sectors")
    assert response.status_code == 200
    assert len(response.json()) == 50
    assert api_client.get("/api/sectors", params={"offset": 50}).json()[0]["name"] == "Sector 050"


def test_circuit_customer_filter_and_reassignment(api_client):
    first = create(api_client, "/api/customers", {"customer_code": "FIRST", "name": "Primero"})
    second = create(api_client, "/api/customers", {"customer_code": "SECOND", "name": "Segundo"})
    # El código no determina el cliente: se respeta exclusivamente customer_id.
    circuit = create(api_client, "/api/circuits", {
        "customer_id": first["id"], "circuit_code": "SECOND.00000", "description": "Internet principal"
    })
    other = create(api_client, "/api/circuits", {
        "customer_id": second["id"], "circuit_code": "SECOND.00001", "description": "Otro enlace"
    })
    assert api_client.get("/api/circuits", params={"customer_id": first["id"]}).json() == [circuit]
    assert api_client.get("/api/circuits", params={"customer_id": second["id"], "search": "iNTERNET"}).json() == []
    updated = api_client.patch(f"/api/circuits/{circuit['id']}", json={"customer_id": second["id"]})
    assert updated.status_code == 200
    assert updated.json()["customer_id"] == second["id"]
    assert updated.json()["circuit_code"] == circuit["circuit_code"]
    assert api_client.get("/api/circuits", params={"customer_id": first["id"]}).json() == []
    assert {c["id"] for c in api_client.get("/api/circuits", params={"customer_id": second["id"]}).json()} == {circuit["id"], other["id"]}
    api_client.patch(f"/api/circuits/{circuit['id']}", json={"active": False})
    assert api_client.get("/api/circuits", params={"customer_id": second["id"], "search": "INTERNET"}).json() == []
    result = api_client.get("/api/circuits", params={
        "customer_id": second["id"], "search": "INTERNET", "include_inactive": True
    }).json()
    assert [c["id"] for c in result] == [circuit["id"]]


def test_circuit_missing_customer(api_client):
    payload = {"customer_id": 999999, "circuit_code": "MANUAL", "description": "Enlace"}
    response = api_client.post("/api/circuits", json=payload)
    assert response.status_code == 404
    assert "Customer" in response.json()["detail"]
    customer = create(api_client, "/api/customers", {"customer_code": "REAL", "name": "Real"})
    circuit = create(api_client, "/api/circuits", {**payload, "customer_id": customer["id"]})
    response = api_client.patch(f"/api/circuits/{circuit['id']}", json={
        "customer_id": 999999, "description": "No debe persistir"
    })
    assert response.status_code == 404
    assert api_client.get(f"/api/circuits/{circuit['id']}").json() == circuit


@pytest.mark.parametrize("customer_id", [0, -1, None, "invalid"])
def test_invalid_customer_id(api_client, customer_id):
    assert api_client.post("/api/circuits", json={
        "customer_id": customer_id, "circuit_code": "MANUAL", "description": "Enlace"
    }).status_code == 422
    if customer_id is not None:
        assert api_client.get("/api/circuits", params={"customer_id": customer_id}).status_code == 422


def test_docs_and_openapi(api_client):
    assert api_client.get("/docs").status_code == 200
    response = api_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert not any(path.startswith("/api/services") for path in paths)
    for name, _, _ in RESOURCES:
        assert set(paths[f"/api/{name}"]) == {"get", "post"}
        assert set(paths[f"/api/{name}/{{id}}"]) == {"get", "patch"}
        assert "delete" not in paths[f"/api/{name}/{{id}}"]


@pytest.mark.parametrize("method, path", [
    ("post", "/api/services"), ("get", "/api/services"),
    ("get", "/api/services/1"), ("patch", "/api/services/1"),
])
def test_services_endpoints_removed(api_client, method, path):
    kwargs = {"json": {"name": "Recurso eliminado"}} if method in {"post", "patch"} else {}
    assert getattr(api_client, method)(path, **kwargs).status_code == 404


def test_create_inactive_catalog(api_client, resource):
    path, _, payload = resource
    item = create(api_client, path, {**payload, "active": False})
    assert item["active"] is False
    assert api_client.get(path).json() == []
    assert api_client.get(path, params={"include_inactive": True}).json() == [item]
    assert api_client.get(f"{path}/{item['id']}").json() == item


def test_create_null_active_rejected(api_client, resource):
    path, _, payload = resource
    assert api_client.post(path, json={**payload, "active": None}).status_code == 422
