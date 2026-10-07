# One image for everything: the API serves the built React app.
#   docker build -t slotbot .            -> production image (Cloud Run)
#   docker compose up                    -> uses the `dev` stage: live reload + debugger on :5678

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS api
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev

# Dev image: same as `api` plus dev tools (debugpy, pytest). Used by docker compose.
FROM api AS dev
RUN uv sync --frozen

FROM api AS prod
COPY --from=web /web/dist /app/static
ENV PORT=8080
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn slotbot.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]
