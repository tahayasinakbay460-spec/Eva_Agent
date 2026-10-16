from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # İç tanımlayıcı (passkey ile kayıtta rastgele); kullanıcı adı olarak gösterilmez.
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="tr")
    # WebAuthn kullanıcı kimliği: rastgele baytlar, kişisel veri yok (W3C WebAuthn §14.6.1).
    webauthn_user_id: Mapped[bytes | None] = mapped_column(
        LargeBinary(64), unique=True, nullable=True
    )
    # E-posta + şifre ile giriş (tehdit modeli §2). E-posta küçük harfe çevrilip saklanır;
    # şifrenin kendisi asla saklanmaz, yalnızca Argon2id özeti (hash) tutulur.
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Kayıttaki beyanlar (§7 yapay zekâ bildirimi, §12 18+). dev-login kullanıcılarında boş.
    age_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ai_disclosure_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
