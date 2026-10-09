"""FastAPI app factory. Run with: uvicorn slotbot.main:create_app --factory"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from slotbot.api import agenda, auth, bookings, jobs, meta, profiles
from slotbot.container import build_container
from slotbot.errors import ConfigError
from slotbot.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]  # values come from the environment
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True) as http:
            container = build_container(settings, http)
            app.state.container = container
            if container.local_loop:
                container.local_loop.start()
            yield
            if container.local_loop:
                await container.local_loop.stop()
            await container.engine.dispose()

    app = FastAPI(title="slotbot", lifespan=lifespan)
    for module in (auth, profiles, agenda, bookings, jobs, meta):
        app.include_router(module.router)
    # Signed (not encrypted) cookie holding the signed-in user's id and email; lax: no cross-site POSTs.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="slotbot_session",
        max_age=30 * 24 * 3600,
        same_site="lax",
        https_only=settings.public_url.startswith("https://"),
    )

    @app.exception_handler(ConfigError)
    async def config_error(_: Request, e: ConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=503)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(_: Request, e: httpx.HTTPError) -> JSONResponse:
        return JSONResponse({"detail": f"upstream service failed: {e}"}, status_code=502)

    @app.get("/health", include_in_schema=False)  # not /healthz: Cloud Run's front end reserves it
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # In the production image the built React app is served by the API itself (one Cloud Run service).
    static = Path(os.environ.get("SLOTBOT_STATIC_DIR", "/app/static"))
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app
