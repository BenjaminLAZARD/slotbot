"""Alembic migrations, run with the app's async engine. URL comes from SLOTBOT_DATABASE_URL."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from slotbot.models import Base, UTCDateTime

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

URL = os.environ.get("SLOTBOT_DATABASE_URL", "postgresql+asyncpg://slotbot:slotbot@localhost:5432/slotbot")


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Write our UTCDateTime decorator as the plain column type it stores."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True, render_item=render_item
    )
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


asyncio.run(main())
