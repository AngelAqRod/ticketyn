from sqlalchemy import Index, func, Boolean, BigInteger, false, true
from sqlalchemy import String, ForeignKey, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class Responsible(CommonFields, Base):
    __tablename__ = "responsibles"

    __table_args__ = (
        ForeignKeyConstraint(['position_id', 'department_id'], ['positions.id', 'positions.department_id'], name='fk_responsibles_position_department'),
        CheckConstraint('position_id IS NULL OR department_id IS NOT NULL', name='position_department'),
        CheckConstraint('NOT access_granted OR (username IS NOT NULL AND password_hash IS NOT NULL AND security_role_id IS NOT NULL)', name='access_complete'),
    )
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departments.id'), index=True)
    position_id: Mapped[int | None] = mapped_column(index=True)
    department: Mapped['Department | None'] = relationship(foreign_keys=[department_id], lazy='joined')
    position: Mapped['Position | None'] = relationship(foreign_keys=[position_id, department_id], lazy='joined', overlaps='department')

    name: Mapped[str] = mapped_column(String, unique=True)
    operational_selectable: Mapped[bool] = mapped_column(Boolean, server_default=true())

    # Persistent administrative grant, independent of operational active/inactive.
    access_granted: Mapped[bool] = mapped_column(Boolean, server_default=false())
    username: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str | None] = mapped_column(String(512))
    security_role_id: Mapped[int | None] = mapped_column(ForeignKey('security_roles.id', ondelete='RESTRICT'), index=True)
    password_change_required: Mapped[bool] = mapped_column(Boolean, server_default=false())
    access_revision: Mapped[int] = mapped_column(BigInteger, server_default='0')

    attention_level: Mapped[str | None] = mapped_column(String(100))


Index('uq_responsibles_name_normalized', func.lower(func.btrim(Responsible.name).collate('C.utf8')), unique=True)

Index('uq_responsibles_username_ci', func.lower(Responsible.username.collate('C.utf8')), unique=True)
