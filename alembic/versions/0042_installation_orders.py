"""Installation documentary orders and independent incoming requests."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

revision = '0042_installation_orders'
down_revision = '0041_profile_preferences'
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.create_table('installation_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reference', sa.String(40), nullable=False, unique=True),
        sa.Column('external_reference', sa.Text()),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('service', sa.Text(), nullable=False), sa.Column('location', sa.Text(), nullable=False),
        sa.Column('contact', sa.Text()), sa.Column('phone', sa.Text()),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False), sa.Column('notes', sa.Text()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('circuit_id', sa.Integer(), sa.ForeignKey('circuits.id'), unique=True), *timestamps())
    op.create_table('installation_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mailbox', sa.String(255), nullable=False), sa.Column('folder', sa.String(255), nullable=False),
        sa.Column('uidvalidity', sa.BigInteger(), nullable=False), sa.Column('uid', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Text()), sa.Column('checksum', sa.String(64), nullable=False),
        sa.Column('sender', sa.Text(), nullable=False), sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False), sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('responsibles.id')),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('installation_orders.id'), unique=True),
        sa.Column('discard_reason', sa.Text()), *timestamps(),
        sa.UniqueConstraint('mailbox', 'folder', 'uidvalidity', 'uid'),
        sa.CheckConstraint("state IN ('PENDING','REVIEWING','PROCESSED','DISCARDED')", name='state_valid'),
        sa.CheckConstraint("(state = 'PROCESSED') = (order_id IS NOT NULL)", name='processed_order'))
    op.create_table('installation_request_drafts',
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('installation_requests.id'), primary_key=True),
        sa.Column('data', sa.JSON(), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('version > 0', name='version_positive'))
    op.create_table('installation_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('installation_orders.id')),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('installation_requests.id')),
        sa.Column('original_name', sa.String(255), nullable=False), sa.Column('media_type', sa.String(150), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False), sa.Column('checksum', sa.String(64), nullable=False),
        sa.Column('storage_key', sa.String(100), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('(order_id IS NULL) <> (request_id IS NULL)', name='one_origin'),
        sa.CheckConstraint('size >= 0', name='size_nonnegative'))
    op.create_table('installation_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('installation_orders.id')),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('installation_requests.id')),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('responsibles.id')),
        sa.Column('action', sa.String(50), nullable=False), sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('order_id IS NOT NULL OR request_id IS NOT NULL', name='has_origin'))
    for table, columns in [('installation_orders', ['customer_id']),
                           ('installation_documents', ['order_id', 'request_id']),
                           ('installation_events', ['order_id', 'request_id'])]:
        for column in columns:
            op.create_index(f'ix_{table}_{column}', table, [column])
    permissions = sa.table('security_permissions', sa.column('code', sa.String), sa.column('description', sa.String))
    vocabulary = (
        ('installation_orders.view', 'installation_orders: Consultar'),
        ('installation_orders.create', 'installation_orders: Crear'),
        ('installation_orders.edit', 'installation_orders: Editar'),
        ('installation_orders.link', 'installation_orders: Gestionar vínculos'),
        ('installation_requests.review', 'installation_requests: Revisar'),
        ('installation_requests.process', 'installation_requests: Procesar'),
        ('installation_requests.discard', 'installation_requests: Descartar'),
        ('incoming_mail.manage', 'incoming_mail: Administrar'),
    )
    op.get_bind().execute(insert(permissions).values([
        {'code': code, 'description': label} for code, label in vocabulary
    ]).on_conflict_do_nothing(index_elements=['code']))


def downgrade():
    # Keep permission rows and custom-role history, following revision 0031.
    for table in ('installation_events', 'installation_documents', 'installation_request_drafts', 'installation_requests', 'installation_orders'):
        op.drop_table(table)
