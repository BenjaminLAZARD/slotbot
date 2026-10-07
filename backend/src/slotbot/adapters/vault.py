import json

from cryptography.fernet import Fernet


class Vault:
    """Symmetric encryption for booking-site credentials stored in the database."""

    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())

    def seal(self, values: dict[str, str]) -> str:
        return self._fernet.encrypt(json.dumps(values).encode()).decode()

    def open(self, token: str) -> dict[str, str]:
        return json.loads(self._fernet.decrypt(token.encode()))
