"""Print the API's OpenAPI schema (used to generate the frontend's TypeScript types)."""

import json

from cryptography.fernet import Fernet

from slotbot.main import create_app
from slotbot.settings import Settings

if __name__ == "__main__":
    print(json.dumps(create_app(Settings(secret_key=Fernet.generate_key().decode())).openapi(), indent=1))
