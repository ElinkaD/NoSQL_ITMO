from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from redis import Redis

from app.config import (
    MONGODB_CONNECT_TIMEOUT_MS,
    MONGODB_DATABSE,
    MONGODB_HOST,
    MONGODB_PASSWORD,
    MONGODB_PORT,
    MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    MONGODB_SOCKET_TIMEOUT_MS,
    MONGODB_USER,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_SOCKET_CONNECT_TIMEOUT,
    REDIS_SOCKET_TIMEOUT,
)


class StorageUnavailableError(RuntimeError):
    def __init__(self, storage_name: str):
        super().__init__(f"{storage_name} unavailable")
        self.storage_name = storage_name


redis_cli = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
    socket_timeout=REDIS_SOCKET_TIMEOUT,
)
mongo_cli = MongoClient(
    host=MONGODB_HOST,
    port=MONGODB_PORT,
    username=MONGODB_USER,
    password=MONGODB_PASSWORD,
    authSource="admin",
    serverSelectionTimeoutMS=MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    connectTimeoutMS=MONGODB_CONNECT_TIMEOUT_MS,
    socketTimeoutMS=MONGODB_SOCKET_TIMEOUT_MS,
)
mongo_db = mongo_cli[MONGODB_DATABSE]
users_collection: Collection = mongo_db["users"]
events_collection: Collection = mongo_db["events"]


def ensure_indexes() -> None:
    users_collection.create_index([("username", ASCENDING)], unique=True)
    events_collection.create_index([("title", ASCENDING)], unique=True)
    events_collection.create_index([("title", ASCENDING), ("created_by", ASCENDING)])
    events_collection.create_index([("created_by", ASCENDING)])
