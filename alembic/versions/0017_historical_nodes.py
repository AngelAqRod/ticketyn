"""Nodo histórico de tickets y FMS, sin inferencias no demostrables."""
from alembic import op
import sqlalchemy as sa
revision = '0017_historical_nodes'
down_revision = '0016_circuit_sectors'
branch_labels = None
depends_on = None
TABLES = ('tickets', 'activations', 'capacity_changes', 'circuit_lifecycle_operations')


def upgrade():
    # circuits.node_id existe desde 0004. Hasta ahora Ticket.node era una
    # propiedad derivada del circuito, no un dato histórico persistido.
    # No copiar el Nodo actual a registros anteriores como si fuera histórico.
    for table in TABLES:
        op.add_column(table, sa.Column('node_id', sa.Integer(), nullable=True))
        op.create_foreign_key(op.f(f'fk_{table}_node_id_nodes'), table, 'nodes', ['node_id'], ['id'])
        op.create_index(f'ix_{table}_node_id', table, ['node_id'])


def downgrade():
    if any(op.get_bind().scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM {table} WHERE node_id IS NOT NULL)')) for table in TABLES):
        raise RuntimeError('Downgrade inseguro: existen Nodos históricos que deben conservarse.')
    for table in reversed(TABLES):
        op.drop_index(f'ix_{table}_node_id', table_name=table)
        op.drop_constraint(op.f(f'fk_{table}_node_id_nodes'), table, type_='foreignkey')
        op.drop_column(table, 'node_id')
