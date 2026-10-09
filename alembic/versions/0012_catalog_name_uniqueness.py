"""Unicidad de nombres sin diferencias de capitalización/espacios externos.

No modifica ni fusiona registros existentes; todos los conflictos se detectan
antes de crear índices. Códigos de clientes y circuitos conservan su semántica.
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_catalog_name_uniqueness'
down_revision = '0011_department_positions'
branch_labels = None
depends_on = None
TABLES = ('customers', 'sectors', 'departments', 'positions', 'incident_types', 'escalation_reasons', 'responsibles', 'nodes')


def upgrade():
    conflicts = []
    db = op.get_bind()
    if not db.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_collation WHERE collname='C.utf8' AND collencoding IN (-1, pg_char_to_encoding('UTF8')))")):
        raise RuntimeError('Falta la collation PostgreSQL C.utf8 necesaria para comparar nombres Unicode. No se han cambiado datos ni creado índices.')
    # Keep the preflight valid until all indexes exist; do not race catalogue writes.
    db.execute(sa.text('LOCK TABLE ' + ', '.join(TABLES) + ' IN SHARE MODE'))
    for table in TABLES:
        scope = 'department_id, ' if table == 'positions' else ''
        rows = db.execute(sa.text(f'SELECT {scope}lower(btrim(name) COLLATE "C.utf8") AS normalized, array_agg(id ORDER BY id) AS ids, array_agg(name ORDER BY id) AS names FROM {table} GROUP BY {scope}lower(btrim(name) COLLATE "C.utf8") HAVING count(*) > 1 ORDER BY {scope}lower(btrim(name) COLLATE "C.utf8")'))
        for row in rows.mappings():
            conflicts.append(f"{table}: departamento={row.get('department_id', 'no aplica')}, ids={row['ids']}, nombres={row['names']}")
    if conflicts:
        raise RuntimeError('No se puede aplicar unicidad de catálogos. Resolver explícitamente estos conflictos sin fusionar ni borrar automáticamente:\n' + '\n'.join(conflicts))
    for table in TABLES:
        expressions = [sa.text('department_id')] if table == 'positions' else []
        op.create_index(f'uq_{table}_name_normalized', table, [*expressions, sa.text('lower(btrim(name) COLLATE "C.utf8")')], unique=True)


def downgrade():
    for table in reversed(TABLES):
        op.drop_index(f'uq_{table}_name_normalized', table_name=table)
