"""Distribution device and port snapshots in FMS activations; historical records preserved.

Revision ID: 0034_activation_distribution
Revises: 0033_distribution_devices_ports
"""
from alembic import op
import sqlalchemy as sa

revision = '0034_activation_distribution'
down_revision = '0033_distribution_devices_ports'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('activations', sa.Column('distribution_recorded', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('activations', sa.Column('distribution_device_name', sa.String(255), nullable=True))
    op.add_column('activations', sa.Column('distribution_port_name', sa.String(255), nullable=True))

    op.create_check_constraint(
        'distribution_recorded_valid', 'activations',
        'distribution_recorded OR (distribution_device_name IS NULL AND distribution_port_name IS NULL)'
    )
    op.create_check_constraint(
        'distribution_device_required', 'activations',
        'distribution_port_name IS NULL OR distribution_device_name IS NOT NULL'
    )


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM activations WHERE distribution_recorded = true)')):
        raise RuntimeError('Downgrade inseguro: existen datos de distribución en activaciones que deben conservarse.')
    op.drop_constraint('distribution_device_required', 'activations', type_='check')
    op.drop_constraint('distribution_recorded_valid', 'activations', type_='check')
    op.drop_column('activations', 'distribution_port_name')
    op.drop_column('activations', 'distribution_device_name')
    op.drop_column('activations', 'distribution_recorded')
