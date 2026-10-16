"""Uppercase only the original, unrenamed default change types."""
from alembic import op
import sqlalchemy as sa

revision = '0024_default_change_types_upper'
down_revision = '0023_change_types'
branch_labels = None
depends_on = None

# 0023 creates an empty identity table and inserts these eight rows in this order
# in the same transaction. Match both original identity and exact original name:
# a renamed default, or a user-created replacement with that name, is untouched.
DEFAULT_NAMES = (
    'Mantenimiento preventivo',
    'Mantenimiento correctivo',
    'Actualización de software',
    'Cambio de configuración',
    'Ampliación de capacidad',
    'Migración de servicios',
    'Pruebas técnicas',
    'Otros',
)


def uppercase_default_types(connection):
    for id, name in enumerate(DEFAULT_NAMES, start=1):
        connection.execute(sa.text('UPDATE change_types SET name=:new_name WHERE id=:id AND name=:old_name'),
                           {'id': id, 'old_name': name, 'new_name': name.upper()})


def upgrade():
    uppercase_default_types(op.get_bind())


def downgrade():
    # Never revert later user edits or infer whether uppercase is user-entered.
    raise RuntimeError('Esta revisión conserva datos operativos: restaurar nombres requiere una revisión explícita.')
