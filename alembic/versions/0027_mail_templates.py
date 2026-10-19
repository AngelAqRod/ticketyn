"""Structured templates; no generated messages or FMS changes.

Revision ID: 0027_mail_templates
Revises: 0026_mail_configuration
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0027_mail_templates'
down_revision = '0026_mail_configuration'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mail_event_config', sa.Column('template', postgresql.JSONB(), nullable=True))


def downgrade():
    populated = op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM mail_event_config WHERE template IS NOT NULL "
        "AND template <> CAST(:empty AS jsonb))"),
        {'empty': '{"version":1,"subject":[],"body":[]}'})
    if populated:
        raise RuntimeError('Elimina explícitamente las plantillas configuradas antes de revertir esta migración.')
    op.drop_column('mail_event_config', 'template')
