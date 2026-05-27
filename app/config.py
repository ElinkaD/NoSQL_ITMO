import os


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value

APP_HOST = require_env("APP_HOST")
APP_PORT = int(require_env("APP_PORT"))
SESSION_TTL = int(require_env("APP_USER_SESSION_TTL"))
APP_LIKE_TTL = int(require_env("APP_LIKE_TTL"))
APP_EVENT_REVIEWS_TTL = int(require_env("APP_EVENT_REVIEWS_TTL"))
APP_RECOMMENDATIONS_TTL = int(require_env("APP_RECOMMENDATIONS_TTL"))

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

CASSANDRA_HOSTS = [host.strip() for host in require_env("CASSANDRA_HOSTS").split(",") if host.strip()]
CASSANDRA_PORT = int(require_env("CASSANDRA_PORT"))
CASSANDRA_USERNAME = require_env("CASSANDRA_USERNAME") or None
CASSANDRA_PASSWORD = require_env("CASSANDRA_PASSWORD") or None
CASSANDRA_KEYSPACE = require_env("CASSANDRA_KEYSPACE")
CASSANDRA_CONSISTENCY = require_env("CASSANDRA_CONSISTENCY").upper()

NEO4J_URL = require_env("NEO4J_URL")
NEO4J_USERNAME = require_env("NEO4J_USERNAME") or None
NEO4J_PASSWORD = require_env("NEO4J_PASSWORD") or None
