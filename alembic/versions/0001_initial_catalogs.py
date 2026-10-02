"""Crear clientes, circuitos, servicios y sectores.

Revision ID: 0001_initial_catalogs
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_catalogs"
down_revision = None
branch_labels = None
depends_on = None


def common_columns():
    return (
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("customer_code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        *common_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("customer_code", name=op.f("uq_customers_customer_code")),
    )
    op.create_index(op.f("ix_customers_name"), "customers", ["name"])
    op.create_table(
        "services",
        sa.Column("name", sa.String(), nullable=False),
        *common_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint("name", name=op.f("uq_services_name")),
    )
    op.create_table(
        "sectors",
        sa.Column("name", sa.String(), nullable=False),
        *common_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sectors")),
        sa.UniqueConstraint("name", name=op.f("uq_sectors_name")),
    )
    op.create_table(
        "circuits",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("circuit_code", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *common_columns(),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name=op.f("fk_circuits_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circuits")),
        sa.UniqueConstraint("circuit_code", name=op.f("uq_circuits_circuit_code")),
    )
    op.create_index(op.f("ix_circuits_customer_id"), "circuits", ["customer_id"])
    op.create_index(op.f("ix_circuits_description"), "circuits", ["description"])


def downgrade() -> None:
    op.drop_index(op.f("ix_circuits_description"), table_name="circuits")
    op.drop_index(op.f("ix_circuits_customer_id"), table_name="circuits")
    op.drop_table("circuits")
    op.drop_table("sectors")
    op.drop_table("services")
    op.drop_index(op.f("ix_customers_name"), table_name="customers")
    op.drop_table("customers")
