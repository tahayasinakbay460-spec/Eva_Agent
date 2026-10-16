# EVA görev çalıştırıcısı (sık kullanılan komutların kısayolları). Windows'ta GNU make
# yoksa, her hedefin altındaki komutları elle çalıştır (hepsi düz uv / npm / docker komutu).

.PHONY: dev infra api web test test-py test-ts lint lint-py lint-ts format migrate migration gen-client eval

infra:            ## postgres (pgvector), redis, minio
	docker compose -f infra/docker-compose.yml up -d

api:              ## FastAPI, :8000 portunda; kod değişince kendini yeniden başlatır
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:              ## Next.js geliştirme sunucusu, :3000 portunda
	cd frontend && npm run dev

dev: infra        ## her şey (api ve web'i iki ayrı terminalde çalıştır)
	@echo "run 'make api' and 'make web' in separate terminals"

test: test-py test-ts

test-py:
	cd backend && uv run pytest -q

test-ts:
	cd frontend && npm run typecheck

lint: lint-py lint-ts

lint-py:
	cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy app tests

lint-ts:
	cd frontend && npm run format:check && npm run lint && npm run typecheck

format:           ## kodu ruff + prettier ile biçimlendir
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

migrate:          ## veritabanını en son migration'a yükselt (alembic upgrade head)
	cd backend && uv run alembic upgrade head

migration:        ## modellerden otomatik yeni migration üret: make migration m="add memories"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

gen-client:       ## OpenAPI şemasından frontend/src/lib/api/schema.d.ts tiplerini üret
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && npm run gen-client

eval:             ## persona / red-team (saldırı senaryosu) testleri (Faz 1+)
	@echo "evals/ not implemented yet"
