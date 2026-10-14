from sqlalchemy import CheckConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class CpeModel(CommonFields, Base):
    __tablename__ = 'cpe_models'
    name: Mapped[str] = mapped_column(String(255))
    __table_args__ = (CheckConstraint("length(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g'))) > 0", name='name_valid'),)


Index('uq_cpe_models_name_normalized', func.lower(func.btrim(func.regexp_replace(func.btrim(CpeModel.name), '[[:space:]]+', ' ', 'g')).collate('C.utf8')), unique=True)
