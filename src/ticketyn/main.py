from fastapi import FastAPI

from ticketyn.api.health import router as health_router
from ticketyn.api.customers import router as customers_router
from ticketyn.api.circuits import router as circuits_router
from ticketyn.api.sectors import router as sectors_router
from ticketyn.api.departments import router as departments_router
from ticketyn.api.incident_types import router as incident_types_router
from ticketyn.api.settings import router as settings_router
from ticketyn.api.tickets import router as tickets_router
from ticketyn.core.config import get_settings


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(title="Ticketyn", version="0.1.0")
    app.include_router(health_router)
    app.include_router(customers_router)
    app.include_router(circuits_router)
    app.include_router(sectors_router)
    app.include_router(departments_router)
    app.include_router(incident_types_router)
    app.include_router(settings_router)
    app.include_router(tickets_router)
    return app


app = create_app()
