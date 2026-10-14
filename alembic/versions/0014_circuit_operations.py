"""Gestión operativa FMS de circuitos, independiente de tickets."""
from alembic import op
import sqlalchemy as sa
revision = '0014_circuit_operations'
down_revision = '0013_escalation_operations'
branch_labels = None
depends_on = None


def operational_columns():
    return [sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
            sa.Column('circuit_id', sa.Integer(), sa.ForeignKey('circuits.id'), nullable=False),
            sa.Column('responsible_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
            sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp())]


def upgrade():
    op.add_column('circuits', sa.Column('initial_capacity', sa.Numeric(18, 6), nullable=True))
    op.add_column('circuits', sa.Column('initial_capacity_unit', sa.String(4), nullable=True))
    op.create_check_constraint(op.f('ck_circuits_initial_capacity_valid'), 'circuits', "(initial_capacity IS NULL AND initial_capacity_unit IS NULL) OR (initial_capacity IS NOT NULL AND initial_capacity > 0 AND initial_capacity <> 'NaN'::numeric AND initial_capacity_unit IS NOT NULL AND initial_capacity_unit IN ('Mbps','Gbps'))")
    op.create_table('deactivation_reasons',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True))
    op.execute('CREATE UNIQUE INDEX uq_deactivation_reasons_name_normalized ON deactivation_reasons (lower(btrim(name) COLLATE "C.utf8"))')
    for name in ('Falta de pago', 'Solicitud del cliente', 'Baja definitiva', 'Cambio de proveedor', 'Migración de servicio'):
        op.execute(sa.text('INSERT INTO deactivation_reasons(name) VALUES (:name)').bindparams(name=name))
    op.create_table('activation_number_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('prefix', sa.String(), nullable=False, server_default='ACT'),
        sa.Column('separator', sa.String(), nullable=False, server_default='-'),
        sa.Column('next_number', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('padding', sa.Integer(), nullable=False, server_default='6'),
        sa.CheckConstraint('id = 1', name=op.f('ck_activation_number_config_singleton')),
        sa.CheckConstraint('next_number > 0', name=op.f('ck_activation_number_config_positive_next_number')),
        sa.CheckConstraint('padding >= 0 AND padding <= 20', name=op.f('ck_activation_number_config_padding_range')))
    op.execute('INSERT INTO activation_number_config(id) VALUES (1)')
    op.create_table('activations', *operational_columns(),
        sa.Column('activation_number', sa.Integer(), nullable=False, unique=True),
        sa.Column('reference', sa.String(), nullable=False, unique=True),
        sa.CheckConstraint('activation_number > 0', name=op.f('ck_activations_positive_number')))
    op.create_table('activation_interventions',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('activation_id', sa.Integer(), sa.ForeignKey('activations.id'), nullable=False),
        sa.Column('responsible_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('content', sa.Text(), nullable=False),
        sa.CheckConstraint('length(btrim(content)) > 0 AND length(content) <= 10000', name=op.f('ck_activation_interventions_content_valid')))
    op.create_index('ix_activation_interventions_chronology', 'activation_interventions', ['activation_id', 'occurred_at', 'id'])
    for field in ('activation_id', 'responsible_id'):
        op.create_index(f'ix_activation_interventions_{field}', 'activation_interventions', [field])
    op.create_table('capacity_changes', *operational_columns(),
        sa.Column('operation_type', sa.String(10), nullable=False),
        sa.Column('previous_capacity', sa.Numeric(18, 6), nullable=True), sa.Column('previous_unit', sa.String(4), nullable=True),
        sa.Column('new_capacity', sa.Numeric(18, 6), nullable=False), sa.Column('new_unit', sa.String(4), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.CheckConstraint("operation_type IN ('INCREASE','DECREASE')", name=op.f('ck_capacity_changes_type_valid')),
        sa.CheckConstraint("new_capacity > 0 AND new_capacity <> 'NaN'::numeric AND new_unit IN ('Mbps','Gbps')", name=op.f('ck_capacity_changes_new_valid')),
        sa.CheckConstraint("(previous_capacity IS NULL AND previous_unit IS NULL AND operation_type = 'INCREASE') OR (previous_capacity IS NOT NULL AND previous_capacity > 0 AND previous_capacity <> 'NaN'::numeric AND previous_unit IS NOT NULL AND previous_unit IN ('Mbps','Gbps'))", name=op.f('ck_capacity_changes_previous_valid')),
        sa.CheckConstraint("previous_capacity IS NULL OR (operation_type = 'INCREASE' AND new_capacity * CASE new_unit WHEN 'Gbps' THEN 1000 ELSE 1 END > previous_capacity * CASE previous_unit WHEN 'Gbps' THEN 1000 ELSE 1 END) OR (operation_type = 'DECREASE' AND new_capacity * CASE new_unit WHEN 'Gbps' THEN 1000 ELSE 1 END < previous_capacity * CASE previous_unit WHEN 'Gbps' THEN 1000 ELSE 1 END)", name=op.f('ck_capacity_changes_direction_valid')))
    op.create_table('circuit_lifecycle_operations', *operational_columns(),
        sa.Column('operation_type', sa.String(12), nullable=False),
        sa.Column('reason_id', sa.Integer(), sa.ForeignKey('deactivation_reasons.id'), nullable=True),
        sa.Column('observations', sa.Text(), nullable=True),
        sa.CheckConstraint("(operation_type = 'DEACTIVATE' AND reason_id IS NOT NULL) OR (operation_type = 'REACTIVATE' AND reason_id IS NULL)", name=op.f('ck_circuit_lifecycle_operations_reason_valid')))
    op.create_index('ix_circuit_lifecycle_operations_reason_id', 'circuit_lifecycle_operations', ['reason_id'])
    for table in ('activations', 'capacity_changes', 'circuit_lifecycle_operations'):
        for field in ('circuit_id', 'responsible_id', 'effective_at'):
            op.create_index(f'ix_{table}_{field}', table, [field])
        name = 'ix_circuit_lifecycle_chronology' if table == 'circuit_lifecycle_operations' else f'ix_{table}_chronology'
        op.create_index(name, table, ['circuit_id', 'effective_at', 'id'])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM activations) OR EXISTS(SELECT 1 FROM capacity_changes) OR EXISTS(SELECT 1 FROM circuit_lifecycle_operations) OR EXISTS(SELECT 1 FROM circuits WHERE initial_capacity IS NOT NULL)')):
        raise RuntimeError('Downgrade inseguro: existen registros FMS o capacidades que deben conservarse.')
    for table in ('activation_interventions', 'circuit_lifecycle_operations', 'capacity_changes', 'activations', 'activation_number_config', 'deactivation_reasons'):
        op.drop_table(table)
    op.drop_constraint(op.f('ck_circuits_initial_capacity_valid'), 'circuits', type_='check')
    op.drop_column('circuits', 'initial_capacity_unit')
    op.drop_column('circuits', 'initial_capacity')
