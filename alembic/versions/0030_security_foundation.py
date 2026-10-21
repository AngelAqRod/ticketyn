"""Security foundation; existing Responsables retain disabled access.

Revision ID: 0030_security_foundation
Revises: 0029_mail_requests
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0030_security_foundation'
down_revision = '0029_mail_requests'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('security_roles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(64), unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('uq_security_roles_name_ci', 'security_roles', [sa.text('lower(name)')], unique=True)
    op.create_table('security_permissions',
        sa.Column('code', sa.String(100), primary_key=True),
        sa.Column('description', sa.String(300), nullable=False))
    op.create_table('security_role_permissions',
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('security_roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_code', sa.String(100), sa.ForeignKey('security_permissions.code', ondelete='CASCADE'), primary_key=True))
    op.create_table('security_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('idle_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('audit_retention_days', sa.Integer(), nullable=False, server_default='365'),
        sa.Column('failure_retention_days', sa.Integer(), nullable=False, server_default='7'),
        sa.CheckConstraint('id = 1', name='singleton'),
        sa.CheckConstraint('idle_minutes >= 3 AND idle_minutes <= 1440', name='idle_range'))
    op.add_column('responsibles', sa.Column('access_granted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('responsibles', sa.Column('username', sa.String(100)))
    op.add_column('responsibles', sa.Column('password_hash', sa.String(512)))
    op.add_column('responsibles', sa.Column('security_role_id', sa.Integer(), sa.ForeignKey('security_roles.id', ondelete='RESTRICT')))
    op.add_column('responsibles', sa.Column('password_change_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('responsibles', sa.Column('access_revision', sa.BigInteger(), nullable=False, server_default='0'))
    op.create_check_constraint('access_complete', 'responsibles', 'NOT access_granted OR (username IS NOT NULL AND password_hash IS NOT NULL AND security_role_id IS NOT NULL)')
    op.create_index('ix_responsibles_security_role_id', 'responsibles', ['security_role_id'])
    op.create_index('uq_responsibles_username_ci', 'responsibles', [sa.text('lower(username COLLATE "C.utf8")')], unique=True)
    op.create_table('security_audit',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='RESTRICT')),
        sa.Column('target_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='RESTRICT')),
        sa.Column('event', sa.String(100), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=False))
    for column in ('occurred_at', 'actor_id', 'event'):
        op.create_index('ix_security_audit_' + column, 'security_audit', [column])
    roles = sa.table('security_roles', sa.column('code', sa.String), sa.column('name', sa.String))
    op.bulk_insert(roles, [
        {'code': 'SUPERADMIN', 'name': 'Superadministrador'},
        {'code': 'ADMIN', 'name': 'Administrador'},
        {'code': 'OPERATOR', 'name': 'Operador'},
        {'code': 'AUDITOR', 'name': 'Auditor / Solo lectura'},
    ])
    op.execute('INSERT INTO security_config (id) VALUES (1)')


def downgrade():
    # Deliberately removes security data; never use as a live rollback procedure.
    op.drop_table('security_audit')
    op.drop_constraint(op.f('ck_responsibles_access_complete'), 'responsibles', type_='check')
    op.drop_index('uq_responsibles_username_ci', table_name='responsibles')
    op.drop_index('ix_responsibles_security_role_id', table_name='responsibles')
    for column in ('access_revision', 'password_change_required', 'security_role_id', 'password_hash', 'username', 'access_granted'):
        op.drop_column('responsibles', column)
    op.drop_table('security_config')
    op.drop_table('security_role_permissions')
    op.drop_table('security_permissions')
    op.drop_table('security_roles')
