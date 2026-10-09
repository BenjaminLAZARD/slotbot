"""Sign-in, the invite list, and who sees which profile — through the real app, on SQLite."""

import asyncio
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from slotbot.main import create_app
from slotbot.models import Base, Profile
from slotbot.ports import Identity
from slotbot.services.accounts import AccountService
from slotbot.settings import Settings

CLIENT_ID = "client-123.apps.googleusercontent.com"


class FakeGoogle:
    """A token is just the email it vouches for; the audience must be the expected one."""

    async def verify(self, token: str, audience: str) -> Identity:
        if not token or audience not in (CLIENT_ID, "http://localhost:8000"):
            raise ValueError("rejected")
        return Identity(email=token, subject=f"sub-{token}", name=token.split("@")[0])


def make_client(tmp_path, **overrides: str) -> Iterator[TestClient]:
    url = f"sqlite+aiosqlite:///{tmp_path}/app.db"

    async def create_tables() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            old = {"calendar_id": "old@group", "provider": "demo"}
            await conn.execute(Profile.__table__.insert().values(name="from before sign-in", config=old))
        await engine.dispose()

    asyncio.run(create_tables())
    settings = Settings(
        secret_key=Fernet.generate_key().decode(),
        database_url=url,
        google_client_id=CLIENT_ID,
        allowed_emails="owner@x.com, friend@x.com",
        triggers="cloudtasks",  # no local timer loop: it would read the (real) calendar in the background
        cloud_tasks_queue="projects/p/locations/l/queues/q",
        **overrides,  # type: ignore[arg-type]
    )
    with TestClient(create_app(settings)) as client:
        c = client.app.state.container  # type: ignore[attr-defined]
        c.identity = FakeGoogle()
        c.accounts = AccountService(c.sessions, c.identity, c.clock, CLIENT_ID, settings.invited)
        yield client


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    yield from make_client(tmp_path)


def sign_in(client: TestClient, email: str) -> int:
    client.post("/auth/logout")
    return client.post("/auth/google", json={"credential": email}).status_code


NEW = {"name": "Mine", "config": {"calendar_id": "cal@group", "provider": "demo"}}


def test_strangers_get_the_landing_page_and_nothing_else(client):
    session = client.get("/auth/session").json()
    assert session["signed_in"] is False and session["google_client_id"] == CLIENT_ID
    assert client.get("/api/profiles").status_code == 401
    assert client.get("/api/meta").status_code == 401
    assert client.post("/api/profiles", json=NEW).status_code == 401


def test_only_invited_google_accounts_get_in(client):
    assert sign_in(client, "eve@x.com") == 403
    assert sign_in(client, "") == 401  # unverifiable credential
    assert sign_in(client, "friend@x.com") == 200
    assert client.get("/auth/session").json()["email"] == "friend@x.com"


def test_people_only_see_their_own_profiles(client):
    assert sign_in(client, "owner@x.com") == 200
    owned = client.get("/api/profiles").json()
    assert [p["name"] for p in owned] == ["from before sign-in"]  # the owner adopts older profiles
    mine = client.post("/api/profiles", json=NEW).json()["id"]

    assert sign_in(client, "friend@x.com") == 200
    assert client.get("/api/profiles").json() == []
    assert client.get(f"/api/profiles/{mine}").status_code == 404
    assert client.get(f"/api/profiles/{mine}/agenda").status_code == 404
    assert client.put(f"/api/profiles/{mine}", json=NEW).status_code == 404
    assert client.delete(f"/api/profiles/{mine}").status_code == 404
    theirs = client.post("/api/profiles", json={**NEW, "name": "Friend's"}).json()["id"]
    assert [p["id"] for p in client.get("/api/profiles").json()] == [theirs]

    client.post("/auth/logout")
    assert client.get("/api/profiles").status_code == 401


def test_jobs_check_the_callers_google_token_once_public(tmp_path):
    clients = make_client(tmp_path, job_token="t0k", job_caller="bot@sa.iam")
    client = next(clients)

    def budget(path: str, bearer: str = "") -> int:
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        return client.post(path, json={"message": {"data": ""}}, headers=headers).status_code

    assert budget("/jobs/budget?token=t0k") == 403  # no Google token
    assert budget("/jobs/budget?token=t0k", "eve@x.com") == 403  # someone else's
    assert budget("/jobs/budget?token=t0k", "bot@sa.iam") == 200
    assert budget("/jobs/budget", "bot@sa.iam") == 403  # the job token is still required
    clients.close()
