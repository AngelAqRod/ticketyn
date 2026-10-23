"""Current distribution topology and scoped operational evidence; no FMS backfill.

Revision ID: 0033_distribution_devices_ports
Revises: 0032_responsible_selectable
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0033_distribution_devices_ports'
down_revision = '0032_responsible_selectable'
branch_labels = None
depends_on = None

MODULES = ('distribution_devices', 'distribution_ports')
ACTIONS = {'view': 'Consultar', 'lookup': 'Consultar selector', 'create': 'Crear',
           'edit': 'Editar', 'move': 'Trasladar', 'set_active': 'Activar o desactivar', 'delete': 'Eliminar'}


def upgrade():
    for table, parent, fk, unique in (
        ('distribution_devices', 'node_id', 'nodes.id', 'uq_distribution_devices_id_node'),
        ('distribution_ports', 'distribution_device_id', 'distribution_devices.id', 'uq_distribution_ports_id_device'),
    ):
        op.create_table(table,
            sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
            sa.Column(parent, sa.Integer(), sa.ForeignKey(fk, ondelete='RESTRICT'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('id', parent, name=unique),
            sa.CheckConstraint("length(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g'))) > 0", name='name_valid'))
        op.create_index(f'uq_{table}_name_normalized', table,
                        [parent, sa.text("lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')) COLLATE \"C.utf8\")")], unique=True)

    op.add_column('circuits', sa.Column('distribution_device_id', sa.Integer()))
    op.add_column('circuits', sa.Column('distribution_port_id', sa.Integer()))
    op.create_check_constraint('distribution_node_required', 'circuits', 'distribution_device_id IS NULL OR node_id IS NOT NULL')
    op.create_check_constraint('distribution_device_required', 'circuits', 'distribution_port_id IS NULL OR distribution_device_id IS NOT NULL')
    op.create_foreign_key('fk_circuits_distribution_device_node', 'circuits', 'distribution_devices',
                          ['distribution_device_id', 'node_id'], ['id', 'node_id'], ondelete='RESTRICT', onupdate='RESTRICT')
    op.create_foreign_key('fk_circuits_distribution_port_device', 'circuits', 'distribution_ports',
                          ['distribution_port_id', 'distribution_device_id'], ['id', 'distribution_device_id'], ondelete='RESTRICT', onupdate='RESTRICT')
    op.create_index('ix_circuits_distribution_device_node', 'circuits', ['distribution_device_id', 'node_id'])
    op.create_index('ix_circuits_distribution_port_device', 'circuits', ['distribution_port_id', 'distribution_device_id'])

    op.create_table('distribution_audit',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('resource_type', sa.String(10), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(12), nullable=False),
        sa.Column('before', postgresql.JSONB()), sa.Column('after', postgresql.JSONB()),
        sa.CheckConstraint("resource_type IN ('DEVICE','PORT','CIRCUIT')", name='resource_valid'),
        sa.CheckConstraint("action IN ('CREATE','EDIT','MOVE','SET_ACTIVE','DELETE','ASSIGN')", name='action_valid'),
        sa.CheckConstraint('resource_id > 0', name='resource_id_valid'))
    op.create_index('ix_distribution_audit_actor_id', 'distribution_audit', ['actor_id'])
    op.create_index('ix_distribution_audit_occurred_at', 'distribution_audit', ['occurred_at'])
    op.create_index('ix_distribution_audit_resource', 'distribution_audit', ['resource_type', 'resource_id', 'occurred_at'])
    permissions = sa.table('security_permissions', sa.column('code', sa.String), sa.column('description', sa.String))
    op.get_bind().execute(postgresql.insert(permissions).values([
        {'code': f'{module}.{action}', 'description': f'{module}: {label}'}
        for module in MODULES for action, label in ACTIONS.items()
    ]).on_conflict_do_nothing(index_elements=['code']))


def downgrade():
    # Removes new distribution data only. Not an operational lossless rollback.
    # As in 0031, keep permission definitions/assignments belonging to custom
    # roles. Older code denies codes outside its vocabulary; do not erase grants.
    op.drop_table('distribution_audit')
    for name in ('ix_circuits_distribution_port_device', 'ix_circuits_distribution_device_node'):
        op.drop_index(name, table_name='circuits')
    for name, kind in (
        ('fk_circuits_distribution_port_device', 'foreignkey'),
        ('fk_circuits_distribution_device_node', 'foreignkey'),
        ('ck_circuits_distribution_device_required', 'check'),
        ('ck_circuits_distribution_node_required', 'check'),
    ):
        op.drop_constraint(op.f(name), 'circuits', type_=kind)
    op.drop_column('circuits', 'distribution_port_id')
    op.drop_column('circuits', 'distribution_device_id')
    op.drop_table('distribution_ports')
    op.drop_table('distribution_devices')
