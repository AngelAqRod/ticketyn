"""Eliminar el catálogo Service: Circuit representa el servicio contratado.

Revision ID: 0002_remove_services
Revises: 0001_initial_catalogs
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_remove_services"
down_revision = "0001_initial_catalogs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("services")


def downgrade() -> None:
    # Reproduce el esquema histórico de 0001; no recupera los datos eliminados.
    op.create_table(
        "services",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint("name", name=op.f("uq_services_name")),
    )
