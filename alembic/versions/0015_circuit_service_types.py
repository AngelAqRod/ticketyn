"""Catálogo de tipos de servicio y asociación opcional con circuitos."""
from alembic import op
import sqlalchemy as sa
revision = '0015_circuit_service_types'
down_revision = '0014_circuit_operations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('service_types',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute('CREATE UNIQUE INDEX uq_service_types_name_normalized ON service_types (lower(btrim(name) COLLATE "C.utf8"))')
    op.add_column('circuits', sa.Column('service_type_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_circuits_service_type_id_service_types'), 'circuits', 'service_types', ['service_type_id'], ['id'])
    op.create_index('ix_circuits_service_type_id', 'circuits', ['service_type_id'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM service_types) OR EXISTS(SELECT 1 FROM circuits WHERE service_type_id IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen tipos de servicio o relaciones que deben conservarse.')
    op.drop_index('ix_circuits_service_type_id', table_name='circuits')
    op.drop_constraint(op.f('fk_circuits_service_type_id_service_types'), 'circuits', type_='foreignkey')
    op.drop_column('circuits', 'service_type_id')
    op.drop_table('service_types')
