import json

from redis.exceptions import RedisError

from app.db import StorageUnavailableError, redis_cli


def delete_cache_key(cache_key: str) -> None:
    try:
        redis_cli.delete(cache_key)
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def read_hash(cache_key: str) -> dict[str, str] | None:
    try:
        cached_value = redis_cli.hgetall(cache_key)
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc

    return cached_value or None


def write_hash(cache_key: str, mapping: dict[str, object], ttl: int) -> None:
    try:
        redis_cli.hset(cache_key, mapping=mapping)
        redis_cli.expire(cache_key, ttl)
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def read_json_hash_field(cache_key: str, field_name: str) -> object | None:
    cached_hash = read_hash(cache_key)
    if not cached_hash:
        return None

    raw_value = cached_hash.get(field_name)
    if raw_value is None:
        return None

    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        delete_cache_key(cache_key)
        return None


def write_json_hash_field(cache_key: str, field_name: str, value: object, ttl: int) -> None:
    write_hash(
        cache_key,
        mapping={field_name: json.dumps(value)},
        ttl=ttl,
    )
