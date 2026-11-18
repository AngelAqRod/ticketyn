"""Editable reception filters for incoming installation requests."""
from alembic import op
import sqlalchemy as sa

revision = '0043_reception_filters'
down_revision = '0042_installation_orders'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('installation_reception_filters',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('senders', sa.JSON(), nullable=False), sa.Column('subjects', sa.JSON(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('responsibles.id')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('id = 1', name='single_row'))


def downgrade():
    op.drop_table('installation_reception_filters')
