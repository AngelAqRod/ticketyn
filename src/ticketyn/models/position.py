from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Position(CommonFields, Base):
    __tablename__ = 'positions'
    __table_args__ = (
        UniqueConstraint('department_id', 'name', name='uq_positions_department_name'),
        UniqueConstraint('id', 'department_id', name='uq_positions_id_department_id'),
        CheckConstraint("escalation_mode IN ('GENERAL', 'INDIVIDUAL')", name='ck_positions_escalation_mode'),
        CheckConstraint('general_escalation_time_minutes IS NULL OR (general_escalation_time_minutes > 0 AND general_escalation_time_minutes <= 10080)', name='ck_positions_general_time'),
    )
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    escalation_mode: Mapped[str] = mapped_column(String(20), server_default='GENERAL')
    general_escalation_time_minutes: Mapped[int | None] = mapped_column(nullable=True)

    department: Mapped['Department'] = relationship(lazy='joined')
    escalation_destinations: Mapped[list['PositionEscalationDestination']] = relationship(
        'PositionEscalationDestination',
        foreign_keys='PositionEscalationDestination.position_id',
        back_populates='position',
        cascade='all, delete-orphan',
        order_by='PositionEscalationDestination.order_index',
        lazy='selectin',
    )

    @property
    def destinations(self):
        return [
            {
                'id': d.id,
                'target_position_id': d.target_position_id,
                'target_position_name': d.target_position.name if d.target_position else '',
                'target_department_name': d.target_position.department.name if d.target_position and d.target_position.department else '',
                'time_minutes': d.time_minutes,
                'order_index': d.order_index,
                'active': d.target_position.active if d.target_position else False,
            }
            for d in self.escalation_destinations
        ]


Index('uq_positions_name_normalized', Position.department_id, func.lower(func.btrim(Position.name).collate('C.utf8')), unique=True)


class PositionEscalationDestination(Base):
    __tablename__ = 'position_escalation_destinations'
    __table_args__ = (
        UniqueConstraint('position_id', 'target_position_id', name='uq_position_escalation_destination'),
        CheckConstraint('position_id != target_position_id', name='ck_position_no_self_escalation'),
        CheckConstraint('time_minutes IS NULL OR (time_minutes > 0 AND time_minutes <= 10080)', name='ck_destination_time_limits'),
        Index('ix_position_destinations_position_id', 'position_id'),
        Index('ix_position_destinations_target_position_id', 'target_position_id'),
    )
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey('positions.id', ondelete='CASCADE'))
    target_position_id: Mapped[int] = mapped_column(ForeignKey('positions.id', ondelete='RESTRICT'))
    time_minutes: Mapped[int | None] = mapped_column(nullable=True)
    order_index: Mapped[int] = mapped_column(server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())

    position: Mapped['Position'] = relationship('Position', foreign_keys=[position_id], back_populates='escalation_destinations')
    target_position: Mapped['Position'] = relationship('Position', foreign_keys=[target_position_id], lazy='joined')
