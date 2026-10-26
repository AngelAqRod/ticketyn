"""Escalation recommendations, 'Escala a' configuration and ACK recognition."""
from alembic import op
import sqlalchemy as sa

revision = '0040_escalation_recommend_ack'
down_revision = '0039_device_templates'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Extend positions table with escalation mode and general time
    op.add_column('positions', sa.Column('escalation_mode', sa.String(20), nullable=False, server_default='GENERAL'))
    op.add_column('positions', sa.Column('general_escalation_time_minutes', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_positions_escalation_mode', 'positions', "escalation_mode IN ('GENERAL', 'INDIVIDUAL')")
    op.create_check_constraint('ck_positions_general_time', 'positions', 'general_escalation_time_minutes IS NULL OR (general_escalation_time_minutes > 0 AND general_escalation_time_minutes <= 10080)')

    # 2. Create position_escalation_destinations table
    op.create_table(
        'position_escalation_destinations',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('time_minutes', sa.Integer(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.UniqueConstraint('position_id', 'target_position_id', name='uq_position_escalation_destination'),
        sa.CheckConstraint('position_id != target_position_id', name='ck_position_no_self_escalation'),
        sa.CheckConstraint('time_minutes IS NULL OR (time_minutes > 0 AND time_minutes <= 10080)', name='ck_destination_time_limits'),
    )
    op.create_index('ix_position_destinations_position_id', 'position_escalation_destinations', ['position_id'])
    op.create_index('ix_position_destinations_target_position_id', 'position_escalation_destinations', ['target_position_id'])

    # 3. Add initial_position_id and closed_seconds to tickets and internal_tickets
    op.add_column('tickets', sa.Column('initial_position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True))
    op.add_column('tickets', sa.Column('closed_seconds', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('ix_tickets_initial_position_id', 'tickets', ['initial_position_id'])

    # Backfill initial_position_id for existing tickets with a responsible having position_id
    op.execute('''
        UPDATE tickets t
        SET initial_position_id = r.position_id
        FROM responsibles r
        WHERE t.responsible_id = r.id AND r.position_id IS NOT NULL AND t.initial_position_id IS NULL
    ''')

    op.add_column('internal_tickets', sa.Column('initial_position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True))
    op.add_column('internal_tickets', sa.Column('closed_seconds', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('ix_internal_tickets_initial_position_id', 'internal_tickets', ['initial_position_id'])

    op.execute('''
        UPDATE internal_tickets t
        SET initial_position_id = r.position_id
        FROM responsibles r
        WHERE t.responsible_id = r.id AND r.position_id IS NOT NULL AND t.initial_position_id IS NULL
    ''')

    # 4. Add position_id to ticket_escalations and internal_escalations
    op.add_column('ticket_escalations', sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_ticket_escalations_position_id', 'ticket_escalations', ['position_id'])

    op.execute('''
        UPDATE ticket_escalations e
        SET position_id = r.position_id
        FROM responsibles r
        WHERE e.recipient_id = r.id AND r.position_id IS NOT NULL AND e.position_id IS NULL
    ''')

    op.add_column('internal_escalations', sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_internal_escalations_position_id', 'internal_escalations', ['position_id'])

    op.execute('''
        UPDATE internal_escalations e
        SET position_id = r.position_id
        FROM responsibles r
        WHERE e.recipient_id = r.id AND r.position_id IS NOT NULL AND e.position_id IS NULL
    ''')

    # 5. Create ticket_escalation_acks table
    op.create_table(
        'ticket_escalation_acks',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('acknowledged_by_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('acknowledged_by_position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('duration_type', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('revoked_by_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.Text(), nullable=True),
        sa.CheckConstraint("duration_type IN ('1H', '4H', '8H', 'INDEFINITE')", name='ck_ticket_ack_duration'),
        sa.CheckConstraint("length(btrim(reason)) > 0 AND length(reason) <= 10000", name='ck_ticket_ack_reason'),
    )
    op.create_index('ix_ticket_acks_ticket_id', 'ticket_escalation_acks', ['ticket_id'])
    op.create_index('ix_ticket_acks_acknowledged_by_id', 'ticket_escalation_acks', ['acknowledged_by_id'])
    op.create_index(
        'uq_ticket_active_ack',
        'ticket_escalation_acks',
        ['ticket_id'],
        unique=True,
        postgresql_where=sa.text('active = true'),
    )

    # 6. Create internal_ticket_escalation_acks table
    op.create_table(
        'internal_ticket_escalation_acks',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('internal_tickets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('acknowledged_by_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('acknowledged_by_position_id', sa.Integer(), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('duration_type', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('revoked_by_id', sa.Integer(), sa.ForeignKey('responsibles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.Text(), nullable=True),
        sa.CheckConstraint("duration_type IN ('1H', '4H', '8H', 'INDEFINITE')", name='ck_internal_ack_duration'),
        sa.CheckConstraint("length(btrim(reason)) > 0 AND length(reason) <= 10000", name='ck_internal_ack_reason'),
    )
    op.create_index('ix_internal_acks_ticket_id', 'internal_ticket_escalation_acks', ['ticket_id'])
    op.create_index('ix_internal_acks_acknowledged_by_id', 'internal_ticket_escalation_acks', ['acknowledged_by_id'])
    op.create_index(
        'uq_internal_active_ack',
        'internal_ticket_escalation_acks',
        ['ticket_id'],
        unique=True,
        postgresql_where=sa.text('active = true'),
    )


def downgrade():
    bind = op.get_bind()
    has_data = bind.scalar(sa.text("""
        SELECT EXISTS (SELECT 1 FROM position_escalation_destinations)
            OR EXISTS (SELECT 1 FROM ticket_escalation_acks)
            OR EXISTS (SELECT 1 FROM internal_ticket_escalation_acks)
    """))
    if has_data:
        raise RuntimeError('Downgrade bloqueado: existen configuraciones de escalamiento o registros de ACK.')

    op.drop_table('internal_ticket_escalation_acks')
    op.drop_table('ticket_escalation_acks')

    op.drop_index('ix_internal_escalations_position_id', table_name='internal_escalations')
    op.drop_column('internal_escalations', 'position_id')

    op.drop_index('ix_ticket_escalations_position_id', table_name='ticket_escalations')
    op.drop_column('ticket_escalations', 'position_id')

    op.drop_index('ix_internal_tickets_initial_position_id', table_name='internal_tickets')
    op.drop_column('internal_tickets', 'closed_seconds')
    op.drop_column('internal_tickets', 'initial_position_id')

    op.drop_index('ix_tickets_initial_position_id', table_name='tickets')
    op.drop_column('tickets', 'closed_seconds')
    op.drop_column('tickets', 'initial_position_id')

    op.drop_table('position_escalation_destinations')

    op.drop_constraint('ck_positions_general_time', 'positions', type_='check')
    op.drop_constraint('ck_positions_escalation_mode', 'positions', type_='check')
    op.drop_column('positions', 'general_escalation_time_minutes')
    op.drop_column('positions', 'escalation_mode')
