"""Sector actual en circuitos e histórico en operaciones FMS."""
from alembic import op
import sqlalchemy as sa
revision = '0016_circuit_sectors'
down_revision = '0015_circuit_service_types'
branch_labels = None
depends_on = None
TABLES = ('circuits', 'activations', 'capacity_changes', 'circuit_lifecycle_operations')


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('sector_id', sa.Integer(), nullable=True))
        op.create_foreign_key(op.f(f'fk_{table}_sector_id_sectors'), table, 'sectors', ['sector_id'], ['id'])
        op.create_index(f'ix_{table}_sector_id', table, ['sector_id'])
    # Nunca elegir arbitrariamente entre sectores contradictorios. FMS antiguo
    # permanece NULL: el sector actual no demuestra su sector histórico.
    op.execute("""UPDATE circuits AS c SET sector_id = history.sector_id
        FROM (SELECT t.circuit_id, min(t.sector_id) AS sector_id
              FROM tickets t JOIN sectors s ON s.id = t.sector_id
              GROUP BY t.circuit_id HAVING count(DISTINCT t.sector_id) = 1) history
        WHERE c.id = history.circuit_id AND c.sector_id IS NULL""")


def downgrade():
    if any(op.get_bind().scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM {table} WHERE sector_id IS NOT NULL)')) for table in TABLES):
        raise RuntimeError('Downgrade inseguro: existen Sectores que deben conservarse.')
    for table in reversed(TABLES):
        op.drop_index(f'ix_{table}_sector_id', table_name=table)
        op.drop_constraint(op.f(f'fk_{table}_sector_id_sectors'), table, type_='foreignkey')
        op.drop_column(table, 'sector_id')
