from datetime import datetime

from sqlalchemy import DateTime, Identity, func, true
from sqlalchemy.orm import Mapped, mapped_column


class CommonFields:
    """Campos técnicos compartidos, con valores generados en PostgreSQL."""

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
