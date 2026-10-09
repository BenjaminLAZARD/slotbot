# CLAUDE.md

Read **HISTORY.md** first (latest entry + open items), then README.md. At the end of each session,
add a dated entry at the top of HISTORY.md: what changed, why, what was verified, open items.

## Ground rules
- Ask Benjamin before choosing frameworks, infra or paid services; propose options with a recommendation.
- Never type the user's passwords into sites; they sign in themselves. Secrets stay in `.env`,
  `secrets/` (gitignored) or the database (encrypted).
- Keep the layering: `domain/` is pure; services depend on `ports.py`; only `container.py` wires
  concrete adapters. New booking sites = one module in `providers/`.

## Commands
- Stack: `docker compose up --build` (UI :5173, API :8000, debugpy :5678, Postgres :5432)
- Backend: `cd backend && uv run pytest && uv run ruff check src tests && uv run ruff format src tests`
- Migration: `cd backend && uv run alembic revision --autogenerate -m "..."` (db container running)
- Frontend: `cd frontend && npm run build && npm run lint`; after API changes `npm run gen:api`
- Cloud infra: `infra/tofu.sh plan` / `apply` (OpenTofu; never change cloud resources with gcloud directly)
- Deploy: push to main (GitHub Actions, when repo variable CD_ENABLED=true) or `gcloud run deploy slotbot --source . --region europe-southwest1 --project divine-camera-228017`
- Cloud bot: `deploy/bot.sh pause|resume|status`; private site: `deploy/proxy.sh`
