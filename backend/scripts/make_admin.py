"""Bir kullanıcıyı yönetici (admin) yapar ya da yöneticiliğini alır. Yalnızca sunucuda,
veritabanına erişimi olan biri çalıştırabilir; API'de böyle bir uç yok (bilerek).

    cd backend
    uv run python scripts/make_admin.py ornek@eposta.com          # admin yap
    uv run python scripts/make_admin.py ornek@eposta.com --revoke # geri al

E-posta yerine kullanıcının görünen adı da verilebilir (passkey ile kayıt olanlar için);
aynı adda birden fazla kişi varsa hiçbir şey yapılmaz.
"""

import argparse
import asyncio

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.database import create_engine, create_session_factory
from app.models.user import User
from app.services import audit


async def main(who: str, revoke: bool) -> int:
    engine = create_engine(get_settings().database_url)
    try:
        async with create_session_factory(engine)() as db:
            result = await db.execute(
                select(User).where(or_(User.email == who.lower(), User.display_name == who))
            )
            users = list(result.scalars().all())
            if len(users) != 1:
                print(f"{len(users)} kullanıcı bulundu; tam olarak bir tane olmalı.")
                return 1
            user = users[0]
            user.role = "user" if revoke else "admin"
            audit.record(
                db,
                action="admin.role_revoked" if revoke else "admin.role_granted",
                target_type="user",
                target_id=user.id,
                user_id=user.id,
                actor_id=None,
                meta={"via": "script"},
            )
            await db.commit()
            print(f"{user.display_name}: rol = {user.role}")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("who", help="e-posta ya da görünen ad")
    parser.add_argument("--revoke", action="store_true", help="yöneticiliği geri al")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.who, args.revoke)))
