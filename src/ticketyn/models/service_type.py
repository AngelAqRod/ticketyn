from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from ticketyn.db.base import Base
from ticketyn.models.common import CommonFields


class ServiceType(CommonFields, Base):
    __tablename__ = 'service_types'
    name: Mapped[str] = mapped_column(String, unique=True)


Index('uq_service_types_name_normalized', func.lower(func.btrim(ServiceType.name).collate('C.utf8')), unique=True)
