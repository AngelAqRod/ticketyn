"""Crear departamentos, tipos de incidencia, numeración y tickets.

Revision ID: 0003_ticket_domain
Revises: 0002_remove_services
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_ticket_domain"
down_revision = "0002_remove_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("departments", "incident_types"):
        op.create_table(
            table,
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
            sa.UniqueConstraint("name", name=op.f(f"uq_{table}_name")),
        )
    op.create_table(
        "ticket_number_config",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("prefix", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("separator", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("next_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("padding", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_ticket_number_config_singleton")),
        sa.CheckConstraint("next_number > 0", name=op.f("ck_ticket_number_config_positive_next_number")),
        sa.CheckConstraint("padding >= 0", name=op.f("ck_ticket_number_config_nonnegative_padding")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_number_config")),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("ticket_number", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("circuit_id", sa.Integer(), nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("incident_type_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ticket_number > 0", name=op.f("ck_tickets_positive_ticket_number")),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name=op.f("ck_tickets_status_values")),
        sa.CheckConstraint("end_at IS NULL OR end_at >= start_at", name=op.f("ck_tickets_valid_dates")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("ticket_number", name=op.f("uq_tickets_ticket_number")),
        sa.UniqueConstraint("reference", name=op.f("uq_tickets_reference")),
        *(
            sa.ForeignKeyConstraint(
                [f"{field}_id"], [f"{table}.id"],
                name=op.f(f"fk_tickets_{field}_id_{table}"),
            ) for field, table in (
                ("customer", "customers"), ("circuit", "circuits"), ("sector", "sectors"),
                ("department", "departments"), ("incident_type", "incident_types"),
            )
        ),
    )
    for field in ("customer", "circuit", "sector", "department", "incident_type"):
        op.create_index(op.f(f"ix_tickets_{field}_id"), "tickets", [f"{field}_id"])


def downgrade() -> None:
    # DROP TABLE elimina también los índices/constraints de esa tabla.
    op.drop_table("tickets")
    op.drop_table("ticket_number_config")
    op.drop_table("incident_types")
    op.drop_table("departments")
