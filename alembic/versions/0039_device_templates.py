"""Reusable equipment templates; installed topology is never rewritten."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert

revision = '0039_device_templates'
down_revision = '0038_port_classification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('distribution_device_templates',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('manufacturer', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('length(btrim(name)) > 0', name='name_valid'))
    op.create_index('uq_distribution_device_templates_name', 'distribution_device_templates',
        [sa.text('lower(btrim(regexp_replace(name, \'[[:space:]]+\', \' \', \'g\')) COLLATE "C.utf8")')], unique=True)
    op.create_table('distribution_device_template_groups',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('distribution_device_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('nomenclature_id', sa.Integer(), sa.ForeignKey('port_nomenclatures.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('definition', JSONB(), nullable=False),
        sa.UniqueConstraint('template_id', 'position'),
        sa.CheckConstraint('position >= 0 AND position < 16', name='position_valid'),
        sa.CheckConstraint("jsonb_typeof(definition) = 'object'", name='definition_valid'))
    op.create_index('ix_distribution_device_template_groups_nomenclature_id', 'distribution_device_template_groups', ['nomenclature_id'])
    op.drop_constraint(op.f('ck_distribution_audit_resource_valid'), 'distribution_audit', type_='check')
    op.create_check_constraint('resource_valid', 'distribution_audit', "resource_type IN ('DEVICE','PORT','CIRCUIT','NOMENCL','TEMPLATE')")
    permissions = sa.table('security_permissions', sa.column('code', sa.String), sa.column('description', sa.String))
    op.get_bind().execute(insert(permissions).values([{'code': f'catalogs.distribution_device_templates.{action}',
        'description': f'Plantillas de equipos: {action}'} for action in ('view', 'lookup', 'create', 'edit')]).on_conflict_do_nothing(index_elements=['code']))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM distribution_device_templates) OR EXISTS(SELECT 1 FROM distribution_audit WHERE resource_type='TEMPLATE')")):
        raise RuntimeError('Downgrade inseguro: existen plantillas o bitácoras que deben conservarse')
    op.drop_constraint(op.f('ck_distribution_audit_resource_valid'), 'distribution_audit', type_='check')
    op.create_check_constraint('resource_valid', 'distribution_audit', "resource_type IN ('DEVICE','PORT','CIRCUIT','NOMENCL')")
    op.drop_table('distribution_device_template_groups')
    op.drop_table('distribution_device_templates')
