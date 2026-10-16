"""Administrable change classification; existing changes remain unclassified."""
from alembic import op
import sqlalchemy as sa

revision = '0023_change_types'
down_revision = '0022_change_control'
branch_labels = None
depends_on = None

INITIAL_TYPES = (
    ('Mantenimiento preventivo', 'Trabajos programados para prevenir fallas'),
    ('Mantenimiento correctivo', 'Corrección de problemas identificados'),
    ('Actualización de software', 'Actualizaciones de firmware o sistemas'),
    ('Cambio de configuración', 'Modificaciones de parámetros de red'),
    ('Ampliación de capacidad', 'Incrementos de capacidad de infraestructura'),
    ('Migración de servicios', 'Traslado de servicios o infraestructura'),
    ('Pruebas técnicas', 'Pruebas de conectividad, redundancia o rendimiento'),
    ('Otros', 'Cambios que no encajan en las categorías anteriores'),
)


def seed_types(connection):
    for name, description in INITIAL_TYPES:
        connection.execute(sa.text('INSERT INTO change_types (name, description) VALUES (:name, :description) ON CONFLICT DO NOTHING'), {'name': name, 'description': description})


def upgrade():
    op.create_table('change_types',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute('CREATE UNIQUE INDEX uq_change_types_name_normalized ON change_types (lower(btrim(name) COLLATE "C.utf8"))')
    op.add_column('maintenance_changes', sa.Column('change_type_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_maintenance_changes_change_type_id_change_types', 'maintenance_changes', 'change_types', ['change_type_id'], ['id'])
    op.create_index('ix_maintenance_changes_change_type_id', 'maintenance_changes', ['change_type_id'])
    seed_types(op.get_bind())


def downgrade():
    raise RuntimeError('Esta revisión conserva datos operativos y clasificaciones: revisar respaldo y recuperación antes de eliminar datos.')
