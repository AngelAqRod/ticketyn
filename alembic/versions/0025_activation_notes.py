"""Optional activation notes, independent of interventions."""
from alembic import op
import sqlalchemy as sa

revision = '0025_activation_notes'
down_revision = '0024_default_change_types_upper'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('activations', sa.Column('activation_notes', sa.Text(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM activations WHERE activation_notes IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen notas de activación que deben conservarse.')
    op.drop_column('activations', 'activation_notes')
