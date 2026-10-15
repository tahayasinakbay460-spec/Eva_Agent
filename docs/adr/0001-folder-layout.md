# ADR 0001: Folder layout uses `backend/` and `frontend/` instead of `services/` and `libs/`

Date: 2026-10-16 · Status: accepted

## Context

CLAUDE.md §3 proposes a monorepo with `apps/`, `services/`, `libs/` and `packages/`.
The project owner is learning the stack and asked for folder names that match the
structure they already know (`backend/app/{core,models,schemas,routers,services}`,
`frontend/`).

## Decision

Keep CLAUDE.md's architecture, map its folders onto familiar names:

| CLAUDE.md §3            | Actual path                       | Notes |
|-------------------------|-----------------------------------|-------|
| `services/api`          | `backend/`                        | FastAPI app in `backend/app/` |
| `libs/eva_core`         | `backend/app/persona/`            | PersonaDefinition, safety core, PersonaCompiler |
| `libs/eva_providers`    | `backend/app/providers/`          | interfaces (`base.py`), adapters (`mock.py`, `anthropic.py`), `registry.py` |
| `services/realtime`     | `realtime/` (Phase 2)             | LiveKit agent, separate process |
| `services/worker`       | `worker/` (Phase 1)               | queue consumer |
| `apps/web`              | `frontend/`                       | Next.js |
| `apps/mobile`           | `mobile/` (when decided, §15)     | Expo |
| `packages/api-client`   | `frontend/src/lib/api/`           | `openapi.json` + generated `schema.d.ts`; `client.ts` is the thin wrapper |
| `config/`, `infra/`, `docs/`, `evals/` | same                | unchanged |

The provider boundary rule (§2.4) is enforced by convention and tests: nothing outside
`backend/app/providers/` imports a vendor SDK.

## Consequences

- No Turborepo/pnpm workspace for now; one Python project and one npm project.
  Revisit when `mobile/` or `packages/ui` appear.
- The learning-phase code was moved to `archive/learning-phase/` and is not imported anywhere.
