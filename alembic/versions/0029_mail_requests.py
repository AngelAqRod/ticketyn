"""Persistent notification coordination; paused until explicit review/resume."""
from alembic import op
import sqlalchemy as sa

revision = '0029_mail_requests'
down_revision = '0028_mail_transport'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mail_processor_control',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('paused', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('reason', sa.String(40), nullable=False, server_default='INITIAL_SETUP'),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('database_oid', sa.BigInteger()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.CheckConstraint('id = 1', name='singleton'))
    op.create_table('mail_notification_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_key', sa.String(100), sa.ForeignKey('mail_event_config.event_key', ondelete='RESTRICT'), nullable=False),
        sa.Column('activation_id', sa.Integer(), sa.ForeignKey('activations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('owner_token', sa.String(64)), sa.Column('error_code', sa.String(40)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('preparing_at', sa.DateTime(timezone=True)), sa.Column('sending_at', sa.DateTime(timezone=True)), sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('event_key', 'activation_id'),
        sa.CheckConstraint("event_key = 'fms.activation.created'", name='event_supported'),
        sa.CheckConstraint("state IN ('PENDING','PREPARING','SENDING','ACCEPTED','FAILED','PARTIAL','UNCERTAIN','CANCELLED')", name='state_valid'),
        sa.CheckConstraint("source IN ('AUTOMATIC','MANUAL')", name='source_valid'),
        sa.CheckConstraint('revision > 0', name='revision_positive'))
    op.create_index('ix_mail_requests_state', 'mail_notification_requests', ['state'])
    op.create_index('ix_mail_requests_pending', 'mail_notification_requests', ['requested_at', 'id'], postgresql_where=sa.text("state = 'PENDING'"))
    op.create_index('ix_mail_notification_requests_activation_id', 'mail_notification_requests', ['activation_id'])
    op.execute(sa.text('INSERT INTO mail_processor_control(id) VALUES(1)'))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM mail_notification_requests)')):
        raise RuntimeError('Hay solicitudes de notificación; revisa y conserva sus datos antes de revertir.')
    op.drop_table('mail_notification_requests')
    op.drop_table('mail_processor_control')
