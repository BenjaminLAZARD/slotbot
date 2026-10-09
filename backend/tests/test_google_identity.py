"""The token checker that guards sign-in and /jobs/*, with our own RSA key standing in for Google's."""

import time

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from google.auth import crypt, jwt

from slotbot.adapters.google_identity import GoogleIdentity

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
PUBLIC = KEY.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


def token(**claims: object) -> str:
    now = int(time.time())
    body = {
        "iss": "https://accounts.google.com",
        "aud": "me",
        "sub": "42",
        "email": "Ana@x.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
        **claims,
    }
    return jwt.encode(crypt.RSASigner.from_string(PEM.decode(), key_id="k1"), body).decode()


def checker(clock, up: list[bool]) -> GoogleIdentity:
    def google(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"k1": PUBLIC.decode()}) if up[0] else httpx.Response(503)

    return GoogleIdentity(httpx.AsyncClient(transport=httpx.MockTransport(google)), clock)


async def test_accepts_a_google_signed_token_for_us(clock):
    who = await checker(clock, [True]).verify(token(), "me")
    assert (who.email, who.subject) == ("ana@x.com", "42")


@pytest.mark.parametrize(
    "claims",
    [{"aud": "someone-else"}, {"iss": "https://evil.example"}, {"email_verified": False}, {"exp": 1}],
)
async def test_rejects_tokens_not_meant_for_us(clock, claims):
    with pytest.raises(ValueError):
        await checker(clock, [True]).verify(token(**claims), "me")


async def test_rejects_garbage(clock):
    for bad in ("", "not.a.jwt", token()[:-5] + "AAAAA"):
        with pytest.raises(ValueError):
            await checker(clock, [True]).verify(bad, "me")


async def test_keeps_working_on_cached_keys_when_google_is_down(clock):
    up = [True]
    google = checker(clock, up)
    await google.verify(token(), "me")
    up[0] = False
    clock.current = clock.current.replace(hour=clock.current.hour + 2)  # cache is stale: refetch fails
    assert (await google.verify(token(), "me")).email == "ana@x.com"
