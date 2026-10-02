def test_health(monkeypatch):
    # No conecta a PostgreSQL ni depende del .env del desarrollador.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test:test@127.0.0.1:1/test",
    )
    from fastapi.testclient import TestClient

    from ticketyn.core.config import get_settings

    get_settings.cache_clear()
    try:
        from ticketyn.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        get_settings.cache_clear()
