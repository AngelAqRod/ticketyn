"""Nodos de distribución y responsables opcionales.

Revision ID: 0004_nodes_responsibles
Revises: 0003_ticket_domain
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_nodes_responsibles"
down_revision = "0003_ticket_domain"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("nodes", "responsibles"):
        op.create_table(table,
            sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
            sa.UniqueConstraint("name", name=op.f(f"uq_{table}_name")))
    for table, field, target in (("circuits", "node_id", "nodes"), ("tickets", "responsible_id", "responsibles")):
        op.add_column(table, sa.Column(field, sa.Integer(), nullable=True))
        op.create_foreign_key(op.f(f"fk_{table}_{field}_{target}"), table, target, [field], ["id"])
        op.create_index(op.f(f"ix_{table}_{field}"), table, [field])


def downgrade():
    for table, field, target in (("tickets", "responsible_id", "responsibles"), ("circuits", "node_id", "nodes")):
        op.drop_index(op.f(f"ix_{table}_{field}"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_{field}_{target}"), table, type_="foreignkey")
        op.drop_column(table, field)
    op.drop_table("responsibles")
    op.drop_table("nodes")
