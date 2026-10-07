"""Booking systems the bot knows. Adding a city = one module implementing ports.Provider."""

from collections.abc import Iterable

import httpx

from slotbot.ports import Provider
from slotbot.providers.demo import DemoProvider
from slotbot.providers.madrid import MadridTennis
from slotbot.settings import Settings


class ProviderRegistry:
    def __init__(self, providers: Iterable[Provider]):
        self._by_key = {p.key: p for p in providers}

    def get(self, key: str) -> Provider:
        try:
            return self._by_key[key]
        except KeyError:
            raise ValueError(f"unknown provider '{key}'") from None

    def all(self) -> list[Provider]:
        return list(self._by_key.values())


def build_registry(http: httpx.AsyncClient, settings: Settings) -> ProviderRegistry:
    return ProviderRegistry([MadridTennis(http, opens_at=settings.madrid_opens_at), DemoProvider()])
