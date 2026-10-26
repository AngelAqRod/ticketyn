"""Minimal personal start-page preference; no change to operational identity."""
from alembic import op
import sqlalchemy as sa

revision = '0041_profile_preferences'
down_revision = '0040_escalation_recommend_ack'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('responsibles', sa.Column('preferred_home_page', sa.String(20), nullable=False,
                                          server_default=sa.text("'DASHBOARD'")))
    op.create_check_constraint('preferred_home_page_valid', 'responsibles', "preferred_home_page IN ('DASHBOARD', 'MY_TICKETS')")


def downgrade():
    op.drop_constraint(op.f('ck_responsibles_preferred_home_page_valid'), 'responsibles', type_='check')
    op.drop_column('responsibles', 'preferred_home_page')
