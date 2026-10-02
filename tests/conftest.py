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

        app = create_app()

        def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()
