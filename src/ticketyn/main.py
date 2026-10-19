from ticketyn.api.cpe_models import router as cpe_models_router
from ticketyn.api.fms_reports import router as fms_reports_router
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from ticketyn.api.service_types import router as service_types_router
from ticketyn.api.fms import router as fms_router
from ticketyn.api.nodes import router as nodes_router
from ticketyn.api.responsibles import router as responsibles_router
from ticketyn.api.positions import router as positions_router

from ticketyn.api.reports import router as reports_router
from ticketyn.api.health import router as health_router
from ticketyn.api.customers import router as customers_router
from ticketyn.api.circuits import router as circuits_router
from ticketyn.api.sectors import router as sectors_router
from ticketyn.api.departments import router as departments_router
from ticketyn.api.incident_types import router as incident_types_router
from ticketyn.api.settings import router as settings_router
from ticketyn.api.tickets import router as tickets_router
from ticketyn.api.ticket_reports import router as ticket_reports_router
from ticketyn.api.ticket_updates import router as ticket_updates_router
from ticketyn.api.escalations import router as escalations_router
from ticketyn.api.escalation_reasons import router as escalation_reasons_router
from ticketyn.api.escalation_stats import router as escalation_stats_router
from ticketyn.core.config import get_settings


def create_app(*, start_notifications=True, notification_engine=None) -> FastAPI:
    get_settings()
    @asynccontextmanager
    async def lifespan(app):
        processor = None
        if start_notifications:
            from ticketyn.db.session import get_engine
            from ticketyn.notifications.processor import NotificationProcessor
            processor = NotificationProcessor(notification_engine if notification_engine is not None else get_engine())
            processor.start()
        try:
            yield
        finally:
            if processor is not None: await asyncio.to_thread(processor.stop)

    app = FastAPI(title="Ticketyn", version="0.5.0", lifespan=lifespan)
    from ticketyn.api.mail_notifications import router as mail_notifications_router
    from ticketyn.api.mail_transport import install_callback_log_filter
    from ticketyn.api import mail_jobs  # registers operational controls on the mail router
    install_callback_log_filter()
    app.include_router(mail_notifications_router)
    from ticketyn.api.activation_notifications import router as activation_notifications_router
    app.include_router(activation_notifications_router)
    from ticketyn.api.internal_tickets import router as internal_router
    from ticketyn.api.internal_incident_types import router as internal_types_router
    from ticketyn.api.providers import router as providers_router
    from ticketyn.api.changes import router as changes_router
    from ticketyn.api.change_reports import router as change_reports_router
    app.include_router(changes_router)
    app.include_router(change_reports_router)
    app.include_router(internal_router)
    app.include_router(internal_types_router)
    app.include_router(providers_router)
    app.include_router(cpe_models_router)
    app.include_router(service_types_router)
    app.include_router(fms_router)
    app.include_router(fms_reports_router)
    app.include_router(escalations_router)
    app.include_router(escalation_reasons_router)
    app.include_router(escalation_stats_router)
    app.include_router(health_router)
    app.include_router(nodes_router)
    app.include_router(responsibles_router)
    app.include_router(positions_router)
    app.include_router(customers_router)
    app.include_router(circuits_router)
    app.include_router(sectors_router)
    app.include_router(departments_router)
    app.include_router(incident_types_router)
    app.include_router(settings_router)
    app.include_router(tickets_router)
    app.include_router(ticket_updates_router)
    app.include_router(ticket_reports_router)
    app.include_router(reports_router)
    return app


app = create_app()
