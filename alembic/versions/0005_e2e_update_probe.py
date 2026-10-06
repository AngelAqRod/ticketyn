"""Columna interna temporal para validar E2E de una actualización con migración.

Revision ID: 0005_e2e_update_probe
Revises: 0004_nodes_responsibles

La aplicación no utiliza esta columna. No modifica datos, relaciones ni defaults.
Su retirada futura deberá hacerse con otra revisión, sin editar esta migración.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_e2e_update_probe"
down_revision = "0004_nodes_responsibles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("_ticketyn_e2e_update_probe", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "_ticketyn_e2e_update_probe")
