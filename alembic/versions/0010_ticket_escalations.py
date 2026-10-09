"""Solicitudes de colaboración independientes de la asignación del ticket."""
from alembic import op
import sqlalchemy as sa

revision = '0010_ticket_escalations'
down_revision = '0009_ticket_resolution'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('responsibles', sa.Column('attention_level', sa.String(100), nullable=True))
    op.create_table('escalation_reasons',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('ticket_escalations',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('recipient_id', sa.Integer(), sa.ForeignKey('responsibles.id'), nullable=False),
        sa.Column('recipient_level', sa.String(100), nullable=True),
        sa.Column('reason_id', sa.Integer(), sa.ForeignKey('escalation_reasons.id'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(8), server_default='ACTIVE', nullable=False),
        sa.UniqueConstraint('id', 'ticket_id', name='uq_ticket_escalations_id_ticket_id'),
        sa.CheckConstraint("status IN ('ACTIVE', 'FINISHED')", name=op.f('ck_ticket_escalations_status_values')),
        sa.CheckConstraint("(status = 'ACTIVE' AND finished_at IS NULL) OR (status = 'FINISHED' AND finished_at IS NOT NULL AND finished_at >= created_at)", name=op.f('ck_ticket_escalations_finish_consistency')),
        sa.CheckConstraint('length(btrim(description)) > 0 AND length(description) <= 10000', name=op.f('ck_ticket_escalations_description_content')))
    op.create_index('ix_ticket_escalations_ticket_chronology', 'ticket_escalations', ['ticket_id', 'created_at', 'id'])
    for field in ('requester_id', 'recipient_id', 'reason_id', 'created_at'):
        op.create_index(f'ix_ticket_escalations_{field}', 'ticket_escalations', [field])
    op.add_column('ticket_updates', sa.Column('escalation_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_ticket_updates_escalation_ticket', 'ticket_updates', 'ticket_escalations', ['escalation_id', 'ticket_id'], ['id', 'ticket_id'])
    op.create_index('ix_ticket_updates_escalation_id', 'ticket_updates', ['escalation_id'])


def downgrade():
    op.drop_index('ix_ticket_updates_escalation_id', table_name='ticket_updates')
    op.drop_constraint('fk_ticket_updates_escalation_ticket', 'ticket_updates', type_='foreignkey')
    op.drop_column('ticket_updates', 'escalation_id')
    op.drop_table('ticket_escalations')
    op.drop_table('escalation_reasons')
    op.drop_column('responsibles', 'attention_level')
