"""Puestos por departamento y solicitantes opcionales; conserva texto legacy."""
from alembic import op
import sqlalchemy as sa

revision = '0011_department_positions'
down_revision = '0010_ticket_escalations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('positions',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('department_id', 'name', name='uq_positions_department_name'),
        sa.UniqueConstraint('id', 'department_id', name='uq_positions_id_department_id'))
    op.create_index('ix_positions_department_id', 'positions', ['department_id'])
    op.add_column('responsibles', sa.Column('department_id', sa.Integer(), nullable=True))
    op.add_column('responsibles', sa.Column('position_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_responsibles_department_id_departments'), 'responsibles', 'departments', ['department_id'], ['id'])
    op.create_foreign_key('fk_responsibles_position_department', 'responsibles', 'positions', ['position_id', 'department_id'], ['id', 'department_id'])
    op.create_check_constraint(op.f('ck_responsibles_position_department'), 'responsibles', 'position_id IS NULL OR department_id IS NOT NULL')
    for field in ('department_id', 'position_id'):
        op.create_index(f'ix_responsibles_{field}', 'responsibles', [field])
    op.alter_column('ticket_escalations', 'requester_id', nullable=True)
    op.add_column('ticket_escalations', sa.Column('recipient_position_name', sa.String(100), nullable=True))
    op.add_column('ticket_escalations', sa.Column('recipient_department_name', sa.Text(), nullable=True))
    # No departmental mapping can be inferred safely from attention_level.
    # Keep it and recipient_level unchanged; new assignments are explicit.


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM ticket_escalations WHERE requester_id IS NULL)')):
        raise RuntimeError('No se puede volver a 0010: existen escalamientos sin solicitante. No se inventarán ni eliminarán registros.')
    op.drop_column('ticket_escalations', 'recipient_department_name')
    op.drop_column('ticket_escalations', 'recipient_position_name')
    op.alter_column('ticket_escalations', 'requester_id', nullable=False)
    for field in ('position_id', 'department_id'):
        op.drop_index(f'ix_responsibles_{field}', table_name='responsibles')
    op.drop_constraint(op.f('ck_responsibles_position_department'), 'responsibles', type_='check')
    op.drop_constraint('fk_responsibles_position_department', 'responsibles', type_='foreignkey')
    op.drop_constraint(op.f('fk_responsibles_department_id_departments'), 'responsibles', type_='foreignkey')
    op.drop_column('responsibles', 'position_id')
    op.drop_column('responsibles', 'department_id')
    op.drop_table('positions')
