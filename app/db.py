from cassandra import ConsistencyLevel
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster, Session
from neo4j import Driver, GraphDatabase
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from redis import Redis

from app.config import (
    CASSANDRA_CONSISTENCY,
    CASSANDRA_HOSTS,
    CASSANDRA_KEYSPACE,
    CASSANDRA_PASSWORD,
    CASSANDRA_PORT,
    CASSANDRA_USERNAME,
    MONGODB_CONNECT_TIMEOUT_MS,
    MONGODB_DATABASE,
    MONGODB_HOST,
    MONGODB_PASSWORD,
    MONGODB_PORT,
    MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    MONGODB_SOCKET_TIMEOUT_MS,
    MONGODB_USER,
    NEO4J_PASSWORD,
    NEO4J_URL,
    NEO4J_USERNAME,
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
    authSource=MONGODB_DATABASE,
    serverSelectionTimeoutMS=MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    connectTimeoutMS=MONGODB_CONNECT_TIMEOUT_MS,
    socketTimeoutMS=MONGODB_SOCKET_TIMEOUT_MS,
)
mongo_db = mongo_cli[MONGODB_DATABASE]
users_collection: Collection = mongo_db["users"]
events_collection: Collection = mongo_db["events"]

consistency_level = getattr(ConsistencyLevel, CASSANDRA_CONSISTENCY, None)
if consistency_level is None:
    raise RuntimeError(f"Unsupported Cassandra consistency level: {CASSANDRA_CONSISTENCY}")

auth_provider = None
if CASSANDRA_USERNAME is not None:
    auth_provider = PlainTextAuthProvider(
        username=CASSANDRA_USERNAME,
        password=CASSANDRA_PASSWORD or "",
    )

cassandra_cluster = Cluster(
    contact_points=CASSANDRA_HOSTS,
    port=CASSANDRA_PORT,
    auth_provider=auth_provider,
)
_cassandra_session: Session | None = None
neo4j_driver: Driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD) if NEO4J_USERNAME is not None else None,
)


def ensure_indexes() -> None:
    users_collection.create_index([("username", ASCENDING)], unique=True)
    users_collection.create_index([("full_name", ASCENDING)])
    events_collection.create_index([("title", ASCENDING)])
    events_collection.create_index([("title", ASCENDING), ("created_by", ASCENDING)])
    events_collection.create_index([("created_by", ASCENDING)])
    events_collection.create_index([("created_by", ASCENDING), ("created_at", ASCENDING)])
    events_collection.create_index([("location.city", ASCENDING), ("created_at", ASCENDING)])
    events_collection.create_index([("category", ASCENDING), ("created_at", ASCENDING)])
    events_collection.create_index([("started_at", ASCENDING)])
    events_collection.create_index([("price", ASCENDING)])


def get_cassandra_session() -> Session:
    global _cassandra_session

    if _cassandra_session is None:
        try:
            _cassandra_session = cassandra_cluster.connect(CASSANDRA_KEYSPACE)
        except Exception as exc:
            raise StorageUnavailableError("cassandra") from exc

    if _cassandra_session is None:
        raise StorageUnavailableError("cassandra")

    return _cassandra_session


def get_neo4j_driver() -> Driver:
    return neo4j_driver
