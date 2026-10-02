import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ticketyn.models import Circuit, Customer, Sector, Service


def test_customer_creation(db_session):
    customer = Customer(customer_code="SGgt-00000", name="Empresa ABC")
    db_session.add(customer)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(Customer, customer.id)
    assert stored.id > 0
    assert stored.customer_code == "SGgt-00000"
    assert stored.name == "Empresa ABC"
    assert stored.active is True
    assert stored.created_at.tzinfo is not None


def test_circuit_creation(db_session):
    customer = Customer(customer_code="SGgt-00000", name="Empresa ABC")
    circuit = Circuit(
        customer=customer, circuit_code="SGgt-00000.00000", description="Enlace principal"
    )
    db_session.add(circuit)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(Circuit, circuit.id)
    assert stored.id > 0
    assert stored.circuit_code == "SGgt-00000.00000"
    assert stored.description == "Enlace principal"
    assert stored.customer_id == customer.id
    assert stored.customer is customer
    assert stored.active is True
    assert stored.created_at.tzinfo is not None


def test_customer_has_multiple_circuits(db_session):
    customer = Customer(customer_code="IDgt-00000", name="Empresa XYZ")
    customer.circuits = [
        Circuit(circuit_code=f"IDgt-00000.{number:05d}", description=f"Enlace {number}")
        for number in range(3)
    ]
    db_session.add(customer)
    db_session.commit()
    db_session.expire_all()

    assert {c.circuit_code for c in customer.circuits} == {
        "IDgt-00000.00000", "IDgt-00000.00001", "IDgt-00000.00002"
    }
    assert all(c.customer_id == customer.id for c in customer.circuits)


def test_circuit_rejects_nonexistent_customer(db_session):
    db_session.add(Circuit(
        customer_id=999999, circuit_code="SGgt-00000.00000", description="Sin cliente"
    ))
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"
    assert error.value.orig.diag.constraint_name == "fk_circuits_customer_id_customers"


@pytest.mark.parametrize("model", [Service, Sector])
def test_catalog_creation(db_session, model):
    item = model(name="Catálogo de prueba")
    db_session.add(item)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(model, item.id)
    assert stored.id > 0
    assert stored.name == "Catálogo de prueba"
    assert stored.active is True
    assert stored.created_at.tzinfo is not None


@pytest.mark.parametrize("model, field, constraint", [
    (Customer, "customer_code", "uq_customers_customer_code"),
    (Circuit, "circuit_code", "uq_circuits_circuit_code"),
    (Service, "name", "uq_services_name"),
    (Sector, "name", "uq_sectors_name"),
])
def test_business_identifier_is_unique(db_session, model, field, constraint):
    def make_item():
        if model is Customer:
            return Customer(customer_code="SGgt-00000", name="Empresa ABC")
        if model is Circuit:
            return Circuit(
                customer=Customer(customer_code="SGgt-00000", name="Empresa ABC"),
                circuit_code="SGgt-00000.00000", description="Enlace principal",
            )
        return model(name="Nombre único")

    first = make_item()
    db_session.add(first)
    db_session.commit()
    # Cambiar el cliente en el segundo circuito prueba unicidad global del código.
    second = make_item()
    if model is Circuit:
        second.customer.customer_code = "IDgt-00000"
    db_session.add(second)
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == constraint
    db_session.rollback()
    assert db_session.scalar(select(model).where(getattr(model, field) == getattr(first, field))) is first


@pytest.mark.parametrize("model, values, missing_field", [
    (Customer, {"name": "Sin código"}, "customer_code"),
    (Customer, {"customer_code": "SGgt-00000"}, "name"),
    (Circuit, {"description": "Sin código"}, "circuit_code"),
    (Circuit, {"circuit_code": "SGgt-00000.00000"}, "description"),
    (Circuit, {"circuit_code": "SGgt-00000.00000", "description": "Sin cliente"}, "customer_id"),
    (Service, {}, "name"),
    (Sector, {}, "name"),
])
def test_required_fields(db_session, model, values, missing_field):
    if model is Circuit and missing_field != "customer_id":
        values = {**values, "customer": Customer(customer_code="SGgt-00000", name="ABC")}
    db_session.add(model(**values))
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == missing_field
