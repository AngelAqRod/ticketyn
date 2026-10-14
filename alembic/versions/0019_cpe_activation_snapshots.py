"""Modelo/configuración CPE y condiciones históricas; registros previos sin inferir."""
from alembic import op
import sqlalchemy as sa
revision = '0019_cpe_activation_snapshots'
down_revision = '0018_recover_ticket_nodes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cpe_models',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g'))) > 0", name=op.f('ck_cpe_models_name_valid')))
    op.execute("CREATE UNIQUE INDEX uq_cpe_models_name_normalized ON cpe_models (lower(btrim(regexp_replace(btrim(name), '[[:space:]]+', ' ', 'g')) COLLATE \"C.utf8\"))")
    op.add_column('circuits', sa.Column('cpe_model_id', sa.Integer(), nullable=True))
    op.add_column('circuits', sa.Column('cpe_configuration', sa.Text(), nullable=True))
    op.create_foreign_key(op.f('fk_circuits_cpe_model_id_cpe_models'), 'circuits', 'cpe_models', ['cpe_model_id'], ['id'])
    op.create_index('ix_circuits_cpe_model_id', 'circuits', ['cpe_model_id'])
    for column in [sa.Column('service_type_name', sa.String(), nullable=True), sa.Column('initial_capacity', sa.Numeric(18,6), nullable=True), sa.Column('initial_capacity_unit', sa.String(4), nullable=True)]:
        op.add_column('activations', column)
    op.create_check_constraint(op.f('ck_activations_initial_capacity_valid'), 'activations', "(initial_capacity IS NULL AND initial_capacity_unit IS NULL) OR (initial_capacity IS NOT NULL AND initial_capacity > 0 AND initial_capacity <> 'NaN'::numeric AND initial_capacity_unit IS NOT NULL AND initial_capacity_unit IN ('Mbps','Gbps'))")
    # No trustworthy prior snapshots exist. Do not infer from mutable circuits.


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM cpe_models) OR EXISTS(SELECT 1 FROM circuits WHERE cpe_model_id IS NOT NULL OR cpe_configuration IS NOT NULL) OR EXISTS(SELECT 1 FROM activations WHERE service_type_name IS NOT NULL OR initial_capacity IS NOT NULL)")):
        raise RuntimeError('Downgrade inseguro: existen datos CPE o condiciones históricas que deben conservarse.')
    op.drop_constraint(op.f('ck_activations_initial_capacity_valid'), 'activations', type_='check')
    for name in ('initial_capacity_unit','initial_capacity','service_type_name'): op.drop_column('activations', name)
    op.drop_index('ix_circuits_cpe_model_id', table_name='circuits')
    op.drop_constraint(op.f('fk_circuits_cpe_model_id_cpe_models'), 'circuits', type_='foreignkey')
    op.drop_column('circuits', 'cpe_configuration')
    op.drop_column('circuits', 'cpe_model_id')
    op.drop_table('cpe_models')
