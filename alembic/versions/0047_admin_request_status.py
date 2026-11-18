"""Administrative request status and optional informative application period."""
from alembic import op
import sqlalchemy as sa

revision = '0047_admin_request_status'
down_revision = '0046_circuit_location'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('admin_requests', sa.Column('status', sa.String(12), nullable=False, server_default='REGISTERED'))
    op.add_column('admin_requests', sa.Column('application_start', sa.Date()))
    op.add_column('admin_requests', sa.Column('application_end', sa.Date()))
    op.create_index('ix_admin_requests_status', 'admin_requests', ['status'])
    op.create_check_constraint('status_valid', 'admin_requests', "status IN ('REGISTERED','IN_PROGRESS','COMPLETED','CANCELLED')")
    op.create_check_constraint('period_valid', 'admin_requests', 'application_start IS NULL OR application_end IS NULL OR application_end >= application_start')


def downgrade():
    op.drop_constraint('ck_admin_requests_period_valid', 'admin_requests')
    op.drop_constraint('ck_admin_requests_status_valid', 'admin_requests')
    op.drop_index('ix_admin_requests_status', 'admin_requests')
    for column in ('application_end', 'application_start', 'status'):
        op.drop_column('admin_requests', column)
