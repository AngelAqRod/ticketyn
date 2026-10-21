def test_health(monkeypatch):
    # No conecta a PostgreSQL ni depende del .env del desarrollador.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@127.0.0.1:1/test",
    )
    from fastapi.testclient import TestClient

    from ticketyn.core.config import get_settings
    from ticketyn.core.version import get_version

    get_settings.cache_clear()
    try:
        from ticketyn.main import create_app

        app = create_app(start_notifications=False)
        assert app.version == get_version()
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        # Importar e iniciar la candidata saludable no requiere una conexión DB.
        with TestClient(create_app(start_notifications=False)) as client:
            assert client.get("/health").status_code == 200
    finally:
        get_settings.cache_clear()
