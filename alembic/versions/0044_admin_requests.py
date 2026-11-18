"""Administrative requests: types, numbering, requests, links and events."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

revision = '0044_admin_requests'
down_revision = '0043_reception_filters'
branch_labels = None
depends_on = None


def now(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table('admin_request_types',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()), now('created_at'),
        sa.Column('name', sa.String(), nullable=False, unique=True), sa.Column('description', sa.Text()))
    op.create_index('uq_admin_request_types_name_normalized', 'admin_request_types',
                    [sa.text("lower(btrim(name) COLLATE \"C.utf8\")")], unique=True)
    op.create_table('admin_request_number_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('prefix', sa.String(), nullable=False, server_default="SOL"),
        sa.Column('separator', sa.String(), nullable=False, server_default='-'),
        sa.Column('next_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('padding', sa.Integer(), nullable=False, server_default='7'),
        sa.CheckConstraint('id = 1', name='singleton'), sa.CheckConstraint('next_number > 0', name='positive_next_number'),
        sa.CheckConstraint('padding >= 0', name='nonnegative_padding'))
    op.create_table('admin_requests',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('ticket_number', sa.Integer(), nullable=False, unique=True),
        sa.Column('reference', sa.String(), nullable=False, unique=True),
        sa.Column('request_date', sa.Date(), nullable=False),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id')),
        sa.Column('circuit_id', sa.Integer(), sa.ForeignKey('circuits.id')),
        sa.Column('type_id', sa.Integer(), sa.ForeignKey('admin_request_types.id'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False), sa.Column('notes', sa.Text()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        now('created_at'), now('updated_at'))
    for column in ('request_date', 'requester_id', 'customer_id', 'circuit_id', 'type_id'):
        op.create_index(f'ix_admin_requests_{column}', 'admin_requests', [column])
    op.create_table('admin_request_links',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('admin_requests.id'), nullable=False),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id')),
        sa.Column('internal_ticket_id', sa.Integer(), sa.ForeignKey('internal_tickets.id')),
        sa.Column('change_id', sa.Integer(), sa.ForeignKey('maintenance_changes.id')),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False), now('created_at'),
        sa.CheckConstraint('num_nonnulls(ticket_id, internal_ticket_id, change_id) = 1', name='one_target'),
        sa.UniqueConstraint('request_id', 'ticket_id', name='uq_admin_request_links_ticket_id'), sa.UniqueConstraint('request_id', 'internal_ticket_id', name='uq_admin_request_links_internal_ticket_id'),
        sa.UniqueConstraint('request_id', 'change_id', name='uq_admin_request_links_change_id'))
    for column in ('request_id', 'ticket_id', 'internal_ticket_id', 'change_id'):
        op.create_index(f'ix_admin_request_links_{column}', 'admin_request_links', [column])
    op.create_table('admin_request_events',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('admin_requests.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False), sa.Column('detail', sa.JSON(), nullable=False), now('created_at'))
    op.create_index('ix_admin_request_events_request_id', 'admin_request_events', ['request_id'])
    permissions = sa.table('security_permissions', sa.column('code', sa.String), sa.column('description', sa.String))
    vocabulary = (
        ('admin_requests.view', 'admin_requests: Consultar'),
        ('admin_requests.create', 'admin_requests: Crear'),
        ('admin_requests.edit', 'admin_requests: Editar'),
        ('admin_requests.link', 'admin_requests: Gestionar vínculos'),
        ('catalogs.admin_request_types.view', 'catalogs.admin_request_types: Consultar'),
        ('catalogs.admin_request_types.create', 'catalogs.admin_request_types: Crear'),
        ('catalogs.admin_request_types.edit', 'catalogs.admin_request_types: Editar'),
        ('catalogs.admin_request_types.lookup', 'catalogs.admin_request_types: Consultar selector'),
        ('settings.admin_request_number.view', 'settings.admin_request_number: Consultar'),
        ('settings.admin_request_number.edit', 'settings.admin_request_number: Editar'),
    )
    op.get_bind().execute(insert(permissions).values([{'code': c, 'description': d} for c, d in vocabulary]).on_conflict_do_nothing(index_elements=['code']))


def downgrade():
    # Keep permission rows and custom-role history, following revision 0031.
    for table in ('admin_request_events', 'admin_request_links', 'admin_requests', 'admin_request_number_config', 'admin_request_types'):
        op.drop_table(table)
