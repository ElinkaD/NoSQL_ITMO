import os


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value

APP_HOST = require_env("APP_HOST")
APP_PORT = int(require_env("APP_PORT"))
SESSION_TTL = int(require_env("APP_USER_SESSION_TTL"))

REDIS_HOST = require_env("REDIS_HOST")
REDIS_PORT = int(require_env("REDIS_PORT"))
REDIS_PASSWORD = require_env("REDIS_PASSWORD") or None
REDIS_DB = int(require_env("REDIS_DB"))
REDIS_SOCKET_CONNECT_TIMEOUT = float(require_env("REDIS_SOCKET_CONNECT_TIMEOUT"))
REDIS_SOCKET_TIMEOUT = float(require_env("REDIS_SOCKET_TIMEOUT"))

MONGODB_HOST = require_env("MONGODB_HOST")
MONGODB_PORT = int(require_env("MONGODB_PORT"))
MONGODB_USER = require_env("MONGODB_USER") or None
MONGODB_PASSWORD = require_env("MONGODB_PASSWORD") or None
MONGODB_DATABASE = require_env("MONGODB_DATABASE")
MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(require_env("MONGODB_SERVER_SELECTION_TIMEOUT_MS"))
MONGODB_CONNECT_TIMEOUT_MS = int(require_env("MONGODB_CONNECT_TIMEOUT_MS"))
MONGODB_SOCKET_TIMEOUT_MS = int(require_env("MONGODB_SOCKET_TIMEOUT_MS"))
