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
from ticketyn.core.version import get_version


def create_app(*, start_notifications=True, notification_engine=None, security_session_factory=None,
               start_audit_retention=None, audit_retention_session_factory=None) -> FastAPI:
    get_settings()
    @asynccontextmanager
    async def lifespan(app):
        from ticketyn.security.passwords import dummy_hash
        await asyncio.to_thread(dummy_hash)
        from ticketyn.security.http import cleanup_loop
        retention, retention_engine = None, None
        # Existing test apps disable background work with start_notifications=False.
        # Retention can be enabled independently with an explicit ephemeral factory.
        if start_audit_retention is True or (start_audit_retention is None and start_notifications):
            from ticketyn.security.retention import AuditRetentionMaintenance
            factory = audit_retention_session_factory or security_session_factory
            if factory is None and notification_engine is not None:
                from sqlalchemy.orm import sessionmaker
                # Preserve any ephemeral schema mapping injected by job tests.
                factory = sessionmaker(notification_engine)
            if factory is None:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from ticketyn.db.session import get_engine
                # One bounded local pool; same configured database, no new service.
                retention_engine = create_engine(get_engine().url, pool_size=1, max_overflow=0,
                                                pool_timeout=1, connect_args={'connect_timeout': 3})
                factory = sessionmaker(retention_engine)
            retention = AuditRetentionMaintenance(factory)
        cleanup = asyncio.create_task(cleanup_loop(app, retention))
        processor = None
        try:
            if start_notifications:
                from ticketyn.db.session import get_engine
                from ticketyn.notifications.processor import NotificationProcessor
                processor = NotificationProcessor(notification_engine if notification_engine is not None else get_engine())
                processor.start()
            yield
        finally:
            cleanup.cancel()
            try:
                await cleanup
            except asyncio.CancelledError:
                pass
            if processor is not None: await asyncio.to_thread(processor.stop)
            if retention_engine is not None: retention_engine.dispose()

    app = FastAPI(title="Ticketyn", version=get_version(), lifespan=lifespan)
    from ticketyn.security.http import install_security
    from ticketyn.api.auth import router as auth_router
    install_security(app, security_session_factory)
    app.include_router(auth_router)
    from ticketyn.api.security_roles import router as security_roles_router
    app.include_router(security_roles_router)
    from ticketyn.api.security_accounts import router as security_accounts_router
    app.include_router(security_accounts_router)
    from ticketyn.api.security_audit import router as security_audit_router
    app.include_router(security_audit_router)
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
    from ticketyn.api.distribution import router as distribution_router
    app.include_router(distribution_router)
    app.include_router(sectors_router)
    app.include_router(departments_router)
    app.include_router(incident_types_router)
    app.include_router(settings_router)
    app.include_router(tickets_router)
    app.include_router(ticket_updates_router)
    app.include_router(ticket_reports_router)
    app.include_router(reports_router)
    from ticketyn.api.port_nomenclatures import router as nomenclature_router
    app.include_router(nomenclature_router)
    from ticketyn.security.routes import validate_coverage
    validate_coverage(app)
    return app


app = create_app()
