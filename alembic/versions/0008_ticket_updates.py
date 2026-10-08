"""Seguimiento permanente de intervenciones de tickets.

Revision ID: 0008_ticket_updates
Revises: 0007_e2e_recovery_probe
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_ticket_updates"
down_revision = "0007_e2e_recovery_probe"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ticket_updates",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=True),
        sa.Column("visibility", sa.String(8), server_default="INTERNAL", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_updates")),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_updates_ticket_id_tickets")),
        sa.ForeignKeyConstraint(["responsible_id"], ["responsibles.id"], name=op.f("fk_ticket_updates_responsible_id_responsibles")),
        sa.CheckConstraint("visibility IN ('INTERNAL', 'PUBLIC')", name=op.f("ck_ticket_updates_visibility_values")),
        sa.CheckConstraint("length(btrim(content)) > 0", name=op.f("ck_ticket_updates_nonempty_content")))
    op.create_index("ix_ticket_updates_ticket_chronology", "ticket_updates", ["ticket_id", "occurred_at", "id"])
    op.create_index(op.f("ix_ticket_updates_responsible_id"), "ticket_updates", ["responsible_id"])


def downgrade():
    op.drop_index(op.f("ix_ticket_updates_responsible_id"), table_name="ticket_updates")
    op.drop_index("ix_ticket_updates_ticket_chronology", table_name="ticket_updates")
    op.drop_table("ticket_updates")
