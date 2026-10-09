from sqlalchemy import Index, func
from sqlalchemy import String, ForeignKey, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Responsible(CommonFields, Base):
    __tablename__ = "responsibles"

    __table_args__ = (
        ForeignKeyConstraint(['position_id', 'department_id'], ['positions.id', 'positions.department_id'], name='fk_responsibles_position_department'),
        CheckConstraint('position_id IS NULL OR department_id IS NOT NULL', name='position_department'),
    )
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departments.id'), index=True)
    position_id: Mapped[int | None] = mapped_column(index=True)
    department: Mapped['Department | None'] = relationship(foreign_keys=[department_id], lazy='joined')
    position: Mapped['Position | None'] = relationship(foreign_keys=[position_id, department_id], lazy='joined', overlaps='department')

    name: Mapped[str] = mapped_column(String, unique=True)

    attention_level: Mapped[str | None] = mapped_column(String(100))


Index('uq_responsibles_name_normalized', func.lower(func.btrim(Responsible.name).collate('C.utf8')), unique=True)
