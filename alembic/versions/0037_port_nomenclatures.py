"""Port nomenclatures and optional classification; existing identities stay intact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, insert

revision = '0037_port_nomenclatures'
down_revision = '0036_customer_activation_notes'
branch_labels = None
depends_on = None


def upgrade():
    conflicts = op.get_bind().execute(sa.text('''SELECT distribution_device_id, array_agg(id ORDER BY id) AS ids
        FROM distribution_ports GROUP BY distribution_device_id,
        lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')) COLLATE "C.utf8")
        HAVING count(*) > 1 LIMIT 10''')).all()
    if conflicts:
        raise RuntimeError(f'Existen puertos equivalentes históricos. Resolver explícitamente antes de migrar: {conflicts}')
    op.create_table('port_nomenclatures',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('prefix', sa.String(200), nullable=False),
        sa.Column('formats', ARRAY(sa.Text()), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('length(btrim(prefix)) > 0', name='prefix_valid'),
        sa.CheckConstraint("formats <@ ARRAY['N','X/Y','X/Y/Z','W/X/Y/Z']::text[] AND (NOT active OR cardinality(formats) > 0)", name='formats_valid'))
    op.create_index('uq_port_nomenclatures_prefix_ci', 'port_nomenclatures', [sa.text('lower(prefix COLLATE "C.utf8")')], unique=True)
    op.add_column('distribution_ports', sa.Column('nomenclature_id', sa.Integer(), nullable=True))
    op.add_column('distribution_ports', sa.Column('numbering_format', sa.String(7), nullable=True))
    op.add_column('distribution_ports', sa.Column('number_components', JSONB(), nullable=True))
    op.create_foreign_key('fk_distribution_ports_nomenclature_id_port_nomenclatures', 'distribution_ports', 'port_nomenclatures', ['nomenclature_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_distribution_ports_nomenclature_id', 'distribution_ports', ['nomenclature_id'])
    op.drop_constraint(op.f('ck_distribution_audit_resource_valid'), 'distribution_audit', type_='check')
    op.create_check_constraint('resource_valid', 'distribution_audit', "resource_type IN ('DEVICE','PORT','CIRCUIT','NOMENCL')")
    permissions = sa.table('security_permissions', sa.column('code', sa.String), sa.column('description', sa.String))
    op.get_bind().execute(insert(permissions).values([{'code': f'catalogs.port_nomenclatures.{action}', 'description': f'Nomenclaturas de puertos: {action}'} for action in ('view','lookup','create','edit','delete')]).on_conflict_do_nothing(index_elements=['code']))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM port_nomenclatures) OR EXISTS(SELECT 1 FROM distribution_audit WHERE resource_type='NOMENCL')")):
        raise RuntimeError('Downgrade inseguro: existen nomenclaturas o bitácoras que deben conservarse')
    op.drop_constraint(op.f('ck_distribution_audit_resource_valid'), 'distribution_audit', type_='check')
    op.create_check_constraint('resource_valid', 'distribution_audit', "resource_type IN ('DEVICE','PORT','CIRCUIT')")
    op.drop_index('ix_distribution_ports_nomenclature_id', table_name='distribution_ports')
    op.drop_constraint('fk_distribution_ports_nomenclature_id_port_nomenclatures', 'distribution_ports', type_='foreignkey')
    for name in ('number_components','numbering_format','nomenclature_id'): op.drop_column('distribution_ports', name)
    op.drop_table('port_nomenclatures')
