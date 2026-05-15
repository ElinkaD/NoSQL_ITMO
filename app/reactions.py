import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.common import parse_include_values
from app.config import APP_LIKE_TTL
from app.db import (
    StorageUnavailableError,
    consistency_level,
    events_collection,
    get_cassandra_session,
    redis_cli,
)


ZERO_REACTIONS = {"likes": 0, "dislikes": 0}

_insert_reaction_statement = None
_select_reactions_statement = None


def should_include_reactions(include_value: str | None) -> bool:
    return "reactions" in parse_include_values(include_value)


def empty_reactions() -> dict[str, int]:
    return dict(ZERO_REACTIONS)


def reactions_cache_key(title: str) -> str:
    title_hash = hashlib.md5(title.encode("utf-8")).hexdigest()
    return f"event:{title_hash}:reactions"


def invalidate_reactions_cache(title: str) -> None:
    try:
        redis_cli.delete(reactions_cache_key(title))
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def _prepare_statements() -> tuple[object, object]:
    global _insert_reaction_statement, _select_reactions_statement

    session = get_cassandra_session()

    if _insert_reaction_statement is None:
        _insert_reaction_statement = session.prepare(
            """
            INSERT INTO event_reactions (event_id, created_by, like_value, created_at)
            VALUES (?, ?, ?, ?)
            """
        )
        _insert_reaction_statement.consistency_level = consistency_level

    if _select_reactions_statement is None:
        _select_reactions_statement = session.prepare(
            """
            SELECT like_value
            FROM event_reactions
            WHERE event_id = ?
            """
        )
        _select_reactions_statement.consistency_level = consistency_level

    return _insert_reaction_statement, _select_reactions_statement


def upsert_event_reaction(event_id: str, user_id: str, like_value: int) -> None:
    insert_statement, _ = _prepare_statements()

    try:
        get_cassandra_session().execute(
            insert_statement,
            (
                event_id,
                user_id,
                like_value,
                datetime.now(timezone.utc),
            ),
        )
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc


def _read_cached_reactions(title: str) -> dict[str, int] | None:
    try:
        cached_reactions = redis_cli.hgetall(reactions_cache_key(title))
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc

    if not cached_reactions:
        return None

    likes = cached_reactions.get("likes")
    dislikes = cached_reactions.get("dislikes")
    try:
        parsed_likes = int(likes)
        parsed_dislikes = int(dislikes)
    except (TypeError, ValueError):
        invalidate_reactions_cache(title)
        return None

    return {"likes": parsed_likes, "dislikes": parsed_dislikes}


def _write_cached_reactions(title: str, reactions: dict[str, int]) -> None:
    try:
        cache_key = reactions_cache_key(title)
        redis_cli.hset(
            cache_key,
            mapping={
                "likes": reactions["likes"],
                "dislikes": reactions["dislikes"],
            },
        )
        redis_cli.expire(cache_key, APP_LIKE_TTL)
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def _load_reactions_from_cassandra(event_ids: list[str]) -> dict[str, int] | None:
    if not event_ids:
        return None

    _, select_statement = _prepare_statements()
    likes = 0
    dislikes = 0
    has_rows = False

    try:
        session = get_cassandra_session()
        for event_id in event_ids:
            for row in session.execute(select_statement, (event_id,)):
                has_rows = True
                if row.like_value == 1:
                    likes += 1
                elif row.like_value == -1:
                    dislikes += 1
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc

    if not has_rows:
        return None

    return {"likes": likes, "dislikes": dislikes}


def get_reactions_by_titles(titles: list[str]) -> dict[str, dict[str, int]]:
    unique_titles = list(dict.fromkeys(titles))
    reactions_by_title: dict[str, dict[str, int]] = {}
    missing_titles: list[str] = []

    for title in unique_titles:
        cached_reactions = _read_cached_reactions(title)
        if cached_reactions is None:
            missing_titles.append(title)
            continue
        reactions_by_title[title] = cached_reactions

    if missing_titles:
        try:
            related_documents = events_collection.find(
                {"title": {"$in": missing_titles}},
                {"_id": 1, "title": 1},
            )
        except PyMongoError as exc:
            raise StorageUnavailableError("mongodb") from exc

        event_ids_by_title: dict[str, list[str]] = defaultdict(list)
        for document in related_documents:
            event_ids_by_title[document["title"]].append(str(document["_id"]))

        for title in missing_titles:
            title_reactions = _load_reactions_from_cassandra(event_ids_by_title.get(title, []))
            if title_reactions is None:
                reactions_by_title[title] = empty_reactions()
                continue

            reactions_by_title[title] = title_reactions
            _write_cached_reactions(title, title_reactions)

    return {title: reactions_by_title.get(title, empty_reactions()) for title in unique_titles}


def refresh_reactions_cache(title: str) -> dict[str, int]:
    try:
        related_documents = events_collection.find(
            {"title": title},
            {"_id": 1},
        )
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    event_ids = [str(document["_id"]) for document in related_documents]
    reactions = _load_reactions_from_cassandra(event_ids)
    if reactions is None:
        reactions = empty_reactions()

    _write_cached_reactions(title, reactions)
    return reactions
