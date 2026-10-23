"""Optional host IP for circuit CPE management; no historical backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET

revision = '0035_cpe_management_ip'
down_revision = '0034_activation_distribution'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('circuits', sa.Column('cpe_management_ip', INET(), nullable=True))
    op.create_check_constraint('cpe_management_ip_host', 'circuits',
        'masklen(cpe_management_ip) = CASE family(cpe_management_ip) WHEN 4 THEN 32 ELSE 128 END')


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM circuits WHERE cpe_management_ip IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen IP de gestión CPE que deben conservarse.')
    op.drop_constraint('cpe_management_ip_host', 'circuits', type_='check')
    op.drop_column('circuits', 'cpe_management_ip')
