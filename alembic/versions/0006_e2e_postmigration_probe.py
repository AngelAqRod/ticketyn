"""Columna interna temporal para el E2E de fallo posterior a migración.

Revision ID: 0006_e2e_postmigration_probe
Revises: 0005_e2e_update_probe

La aplicación no utiliza esta columna. No transforma datos ni relaciones.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_e2e_postmigration_probe"
down_revision = "0005_e2e_update_probe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("_ticketyn_e2e_postmigration_probe", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "_ticketyn_e2e_postmigration_probe")
