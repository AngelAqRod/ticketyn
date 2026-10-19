"""OAuth settings and bounded test coordination; no jobs or message history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0028_mail_transport'
down_revision = '0027_mail_templates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mail_transport_config', sa.Column('oauth_settings', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column('mail_transport_config', sa.Column('oauth_status', sa.String(32), nullable=False, server_default='UNCONFIGURED'))
    op.add_column('mail_transport_config', sa.Column('test_not_before', sa.DateTime(timezone=True)))
    op.add_column('mail_transport_config', sa.Column('test_lease_until', sa.DateTime(timezone=True)))
    op.add_column('mail_transport_config', sa.Column('test_lease_token', sa.String(64)))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM mail_transport_config WHERE oauth_settings <> '{}'::jsonb OR oauth_status <> 'UNCONFIGURED' OR oauth_credentials_encrypted IS NOT NULL OR test_lease_until > clock_timestamp())")):
        raise RuntimeError('Desconecta y elimina explícitamente la configuración OAuth2 y espera a que terminen las pruebas antes de revertir.')
    for column in ('test_lease_token', 'test_lease_until', 'test_not_before', 'oauth_status', 'oauth_settings'):
        op.drop_column('mail_transport_config', column)
