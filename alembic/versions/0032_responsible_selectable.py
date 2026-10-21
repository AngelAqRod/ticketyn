"""Independent operational availability; preserve all existing identities.

Revision ID: 0032_responsible_selectable
Revises: 0031_role_permissions
"""
from alembic import op
import sqlalchemy as sa

revision = '0032_responsible_selectable'
down_revision = '0031_role_permissions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('responsibles', sa.Column('operational_selectable', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('responsibles', 'operational_selectable')
