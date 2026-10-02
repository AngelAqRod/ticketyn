from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ticketyn.api.ticket_data import create_ticket
from ticketyn.db.base import Base
from ticketyn.models import Circuit, Customer, Department, IncidentType, Sector, Ticket, TicketNumberConfig


@pytest.fixture
def concurrent_database(postgres_engine):
    """Datos confirmados para conexiones distintas, solo en el clúster temporal."""
    schema = f"concurrency_test_{uuid4().hex}"
    scoped_engine = postgres_engine.execution_options(schema_translate_map={None: schema})
    with scoped_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        Base.metadata.create_all(connection)
    try:
        with Session(scoped_engine) as session:
            customer = Customer(customer_code="CONCURRENT", name="Cliente de prueba")
            circuit = Circuit(customer=customer, circuit_code="MANUAL", description="Enlace de prueba")
            sector = Sector(name="Sector de prueba")
            department = Department(name="Departamento de prueba")
            incident = IncidentType(name="Tipo de prueba")
            session.add_all([circuit, sector, department, incident])
            session.commit()
            payload = {
                "customer_id": customer.id, "circuit_id": circuit.id, "sector_id": sector.id,
                "department_id": department.id, "incident_type_id": incident.id,
                "title": "Prueba concurrente", "description": "Transacciones independientes",
                "start_at": datetime(2020, 1, 1, tzinfo=timezone.utc), "end_at": None, "status": "OPEN",
            }
        yield scoped_engine, payload
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_concurrent_ticket_creation_and_lazy_singleton(concurrent_database):
    engine, payload = concurrent_database
    workers = 8
    barrier = Barrier(workers)

    def create_one(_):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            ticket = create_ticket(session, payload.copy())
            return ticket.ticket_number, ticket.reference

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(create_one, range(workers)))

    assert sorted(number for number, _ in results) == list(range(1, workers + 1))
    assert len({reference for _, reference in results}) == workers
    with Session(engine) as session:
        assert len(list(session.scalars(select(Ticket)))) == workers
        configs = list(session.scalars(select(TicketNumberConfig)))
        assert len(configs) == 1
        assert configs[0].next_number == workers + 1
        assert configs[0].prefix == configs[0].separator == ""
