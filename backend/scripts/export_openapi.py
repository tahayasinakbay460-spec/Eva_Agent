"""OpenAPI şemasını frontend/src/lib/api/openapi.json dosyasına yazar.

Frontend'deki TypeScript istemci tipleri bu dosyadan üretilir (frontend/ içinde
``npm run gen-client``). Böylece API'nin tek doğru kaynağı FastAPI şeması olarak kalır
(CLAUDE.md §13).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.main import create_app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api" / "openapi.json"


def main() -> None:
    app = create_app(Settings(_env_file=None, env="test", llm_provider_override="mock"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
