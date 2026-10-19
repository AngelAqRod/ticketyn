"""Administrative mail configuration only; no delivery or FMS changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0026_mail_configuration'
down_revision = '0025_activation_notes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mail_transport_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host', sa.String(253)),
        sa.Column('port', sa.Integer(), nullable=False, server_default=sa.text('587')),
        sa.Column('security', sa.String(20), nullable=False, server_default=sa.text("'STARTTLS'")),
        sa.Column('allow_unencrypted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('sender_email', sa.String(254)),
        sa.Column('sender_name', sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column('auth_method', sa.String(30), nullable=False, server_default=sa.text("'NONE'")),
        sa.Column('provider', sa.String(30)),
        sa.Column('username', sa.String(254)),
        sa.Column('smtp_password_encrypted', sa.Text()),
        sa.Column('oauth_credentials_encrypted', sa.Text()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='singleton'),
        sa.CheckConstraint('port BETWEEN 1 AND 65535', name='port_valid'),
        sa.CheckConstraint("security IN ('STARTTLS','IMPLICIT_TLS','NONE')", name='security_valid'),
        sa.CheckConstraint("auth_method IN ('NONE','PASSWORD','OAUTH2_DELEGATED','OAUTH2_APPLICATION')", name='auth_valid'),
        sa.CheckConstraint("security <> 'NONE' OR allow_unencrypted", name='unencrypted_opt_in'))
    op.create_table('mail_event_config',
        sa.Column('event_key', sa.String(100), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False, server_default=sa.text("'DISABLED'")),
        sa.Column('to_recipients', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('cc_recipients', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('bcc_recipients', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.PrimaryKeyConstraint('event_key'),
        sa.CheckConstraint("mode IN ('AUTOMATIC','MANUAL','DISABLED')", name='mode_valid'),
        sa.CheckConstraint("jsonb_typeof(to_recipients) = 'array' AND jsonb_typeof(cc_recipients) = 'array' AND jsonb_typeof(bcc_recipients) = 'array'", name='recipients_arrays'))
    op.execute("INSERT INTO mail_transport_config(id) VALUES(1)")
    op.execute("INSERT INTO mail_event_config(event_key) VALUES('fms.activation.created')")


def downgrade():
    # Preserve real configuration/credentials: only untouched defaults can be removed.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM mail_transport_config WHERE host IS NOT NULL OR sender_email IS NOT NULL OR sender_name <> '' OR port <> 587 OR security <> 'STARTTLS' OR allow_unencrypted OR auth_method <> 'NONE' OR provider IS NOT NULL OR username IS NOT NULL OR smtp_password_encrypted IS NOT NULL OR oauth_credentials_encrypted IS NOT NULL)")) or connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM mail_event_config WHERE event_key <> 'fms.activation.created' OR mode <> 'DISABLED' OR to_recipients <> '[]'::jsonb OR cc_recipients <> '[]'::jsonb OR bcc_recipients <> '[]'::jsonb)")):
        raise RuntimeError('Downgrade inseguro: existe configuración de correo que debe conservarse.')
    op.drop_table('mail_event_config')
    op.drop_table('mail_transport_config')
