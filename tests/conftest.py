import getpass
import shutil
import subprocess

import pytest
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

from ticketyn.db.base import Base
from ticketyn import models  # noqa: F401 -- registra los modelos


@pytest.fixture(scope="session")
def postgres_engine(tmp_path_factory):
    """Clúster descartable; nunca lee DATABASE_URL ni el .env local."""
    for executable in ("initdb", "pg_ctl"):
        if shutil.which(executable) is None:
            pytest.fail(f"Falta {executable}: instala PostgreSQL para ejecutar estas pruebas")

    root = tmp_path_factory.mktemp("ticketyn-postgres")
    data = root / "data"
    socket = root / "socket"
    socket.mkdir()
    subprocess.run(
        ["initdb", "-D", str(data), "--auth=trust", "--encoding=UTF8", "--locale=C"],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["pg_ctl", "-D", str(data), "-l", str(root / "postgres.log"),
         "-o", f"-h '' -k {socket} -p 55439", "-w", "start"],
        check=True, capture_output=True, text=True,
    )
    engine = create_engine(URL.create(
        "postgresql+psycopg", username=getpass.getuser(), database="postgres",
        query={"host": str(socket), "port": "55439"},
    ))
    try:
        # Solo en este clúster temporal: no se ejecutan migraciones.
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"],
            check=True, capture_output=True, text=True,
        )


@pytest.fixture
def db_session(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def api_client(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    from ticketyn.core.config import get_settings
    from ticketyn.db.session import get_session

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/test")
    get_settings.cache_clear()
    try:
        from ticketyn.main import create_app

        app = create_app(start_notifications=False)

        def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        with TestClient(app) as client:
            from security_helpers import authenticate_test_client
            authenticate_test_client(app, client, db_session.get_bind())
            yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def ticket_payload(api_client):
    def create(path, body):
        response = api_client.post(path, json=body)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    customer_id = create("/api/customers", {"customer_code": "TEST-CUSTOMER", "name": "Cliente de prueba"})
    node_id = create("/api/nodes", {"name": "Nodo de prueba"})
    sector_id = create("/api/sectors", {"name": "Sector de prueba"})
    circuit_id = create("/api/circuits", {
        "node_id": node_id, "sector_id": sector_id, "customer_id": customer_id, "circuit_code": "MANUAL-CIRCUIT", "description": "Enlace de prueba"
    })
    return {
        "customer_id": customer_id,
        "circuit_id": circuit_id,
        "sector_id": sector_id,
        "node_id": node_id,
        "department_id": create("/api/departments", {"name": "Departamento de prueba"}),
        "incident_type_id": create("/api/incident-types", {"name": "Tipo de prueba"}),
        "title": "Caída de servicio",
        "description": "Sin conectividad",
        "start_at": "2020-01-01T12:00:00+00:00",
        "status": "OPEN",
    }


@pytest.fixture
def numbered_port(api_client):
    """Create through the same preview/confirm contract as the port form."""
    def create(device_id, prefix='sfp+', numbering_format='N', positions=(), number=1, description=None):
        catalogs = api_client.get('/api/port-nomenclatures?include_inactive=true&limit=200').json()
        catalog = next((row for row in catalogs if row['prefix'] == prefix), None)
        if catalog is None:
            response = api_client.post('/api/port-nomenclatures', json={
                'name': prefix, 'prefix': prefix, 'formats': ['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z']})
            assert response.status_code == 201, response.text
            catalog = response.json()
        payload = {'distribution_device_id': device_id, 'nomenclature_id': catalog['id'],
                   'numbering_format': numbering_format, 'positions': list(positions), 'start': number,
                   'description': description}
        checked = api_client.post('/api/distribution-ports/preview', json=payload)
        assert checked.status_code == 200, checked.text
        response = api_client.post('/api/distribution-ports', json={**payload, 'preview_token': checked.json()['preview_token']})
        assert response.status_code == 201, response.text
        return response.json()
    return create
