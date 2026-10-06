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
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert "Fallo E2E deliberado posterior a migración" in response.json()["message"]
        # El fallo es permanente; importar e iniciar la aplicación sigue siendo válido.
        with TestClient(create_app()) as client:
            assert client.get("/health").status_code == 503
    finally:
        get_settings.cache_clear()
