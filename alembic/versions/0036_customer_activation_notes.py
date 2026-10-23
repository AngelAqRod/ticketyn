"""Explicit customer-facing activation notes; no backfill from internal notes."""
from alembic import op
import sqlalchemy as sa

revision = '0036_customer_activation_notes'
down_revision = '0035_cpe_management_ip'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('customer_activation_notes', 'customer_name_snapshot', 'circuit_code_snapshot'):
        op.add_column('activations', sa.Column(name, sa.Text(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM activations WHERE customer_activation_notes IS NOT NULL OR customer_name_snapshot IS NOT NULL OR circuit_code_snapshot IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen notas o instantáneas de cliente que deben conservarse.')
    for name in ('circuit_code_snapshot', 'customer_name_snapshot', 'customer_activation_notes'):
        op.drop_column('activations', name)
