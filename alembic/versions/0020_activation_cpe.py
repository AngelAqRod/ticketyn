"""CPE histórico de activación, sin inferir datos de registros anteriores."""
from alembic import op
import sqlalchemy as sa

revision = '0020_activation_cpe'
down_revision = '0019_cpe_activation_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('activations', sa.Column('cpe_activation', sa.Text(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM activations WHERE cpe_activation IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen snapshots CPE de activación que deben conservarse.')
    op.drop_column('activations', 'cpe_activation')
