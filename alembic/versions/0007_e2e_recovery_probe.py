"""Columna interna temporal para validar el E2E de recovery con updater v2.

Revision ID: 0007_e2e_recovery_probe
Revises: 0006_e2e_postmigration_probe

La aplicación no utiliza esta columna. No transforma datos ni relaciones.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_e2e_recovery_probe"
down_revision = "0006_e2e_postmigration_probe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("_ticketyn_e2e_recovery_probe", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "_ticketyn_e2e_recovery_probe")
