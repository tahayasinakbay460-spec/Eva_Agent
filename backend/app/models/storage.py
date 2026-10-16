import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow
from app.models.base import UTCDateTime


class UserDataKey(Base):
    """Kullanıcının dosyalarını şifreleyen veri anahtarı, ana anahtarla sarmalanmış hâlde.

    Düz anahtar asla saklanmaz. Satır silinirse kullanıcının şifreli dosyaları kalıcı olarak
    okunamaz (kripto-silme, §11.4).
    """

    __tablename__ = "user_data_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary(128), nullable=False)
    # Hangi ana anahtarla sarıldı (anahtar rotasyonunda eski/yeni ayırt edilsin diye).
    kek_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
