"""Resolución y textos explícitamente autorizados para reportes de cliente.

Revision ID: 0009_ticket_resolution
Revises: 0008_ticket_updates
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_ticket_resolution"
down_revision = "0008_ticket_updates"
branch_labels = None
depends_on = None

FIELDS = ("resolution", "customer_description", "customer_resolution")


def upgrade():
    for field in FIELDS:
        op.add_column("tickets", sa.Column(field, sa.Text(), nullable=True))
        op.create_check_constraint(op.f(f"ck_tickets_{field}_content"), "tickets",
            f"{field} IS NULL OR (length(btrim({field})) > 0 AND length({field}) <= 10000)")


def downgrade():
    for field in reversed(FIELDS):
        op.drop_constraint(op.f(f"ck_tickets_{field}_content"), "tickets", type_="check")
        op.drop_column("tickets", field)
