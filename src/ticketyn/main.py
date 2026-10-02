from fastapi import FastAPI

from ticketyn.api.health import router as health_router
from ticketyn.api.customers import router as customers_router
from ticketyn.api.circuits import router as circuits_router
from ticketyn.api.services import router as services_router
from ticketyn.api.sectors import router as sectors_router
from ticketyn.core.config import get_settings


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(title="Ticketyn", version="0.1.0")
    app.include_router(health_router)
    app.include_router(customers_router)
    app.include_router(circuits_router)
    app.include_router(services_router)
    app.include_router(sectors_router)
    return app


app = create_app()
