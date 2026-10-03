from tempfile import SpooledTemporaryFile
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from starlette.background import BackgroundTask

from ticketyn.api.crud import DBSession
from ticketyn.api.report_data import report_summary
from ticketyn.api.report_exports import export_pdf, export_xlsx
from ticketyn.schemas.report import ReportFilters, ReportSummary

router = APIRouter(prefix='/api/reports', tags=['reports'])


def read_snapshot(session):
    # Sesiones normales: las agregaciones y el detalle de cada exportación ven
    # un único snapshot. Los tests ya tienen una Connection/transacción aislada.
    if isinstance(session.get_bind(), Engine):
        session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})


@router.get('/summary', response_model=ReportSummary)
def summary(session: DBSession, filters: Annotated[ReportFilters, Query()]):
    read_snapshot(session)
    return report_summary(session, filters)


@router.get('/export/{format}')
def export(session: DBSession, format: Literal['pdf', 'xlsx'], filters: Annotated[ReportFilters, Query()]):
    read_snapshot(session)
    summary = report_summary(session, filters)
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        (export_pdf if format == 'pdf' else export_xlsx)(session, filters, summary, output)
        output.seek(0)
    except Exception:
        output.close()
        raise
    def chunks():
        try:
            while chunk := output.read(65536):
                yield chunk
        finally:
            output.close()
    name = 'nodo' if filters.node_id else 'responsable' if filters.responsible_id else 'sector' if filters.sector_id else 'general'
    media = 'application/pdf' if format == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return StreamingResponse(chunks(), media_type=media,
        headers={'Content-Disposition': f'attachment; filename="ticketyn-{name}.{format}"'},
        background=BackgroundTask(output.close))
