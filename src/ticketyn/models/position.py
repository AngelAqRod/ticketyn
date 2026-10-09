from sqlalchemy import Index, func
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Position(CommonFields, Base):
    __tablename__ = 'positions'
    __table_args__ = (
        UniqueConstraint('department_id', 'name', name='uq_positions_department_name'),
        UniqueConstraint('id', 'department_id', name='uq_positions_id_department_id'),
    )
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    department: Mapped['Department'] = relationship(lazy='joined')


Index('uq_positions_name_normalized', Position.department_id, func.lower(func.btrim(Position.name).collate('C.utf8')), unique=True)
