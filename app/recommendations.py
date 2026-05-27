from collections import defaultdict

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.cache import read_json_hash_field, write_json_hash_field
from app.common import parse_object_id, parse_rfc3339
from app.config import APP_RECOMMENDATIONS_TTL
from app.db import StorageUnavailableError, events_collection
from app.event_serializers import serialize_event
from app.neo4j_client import run_query
from app.sessions import get_current_user_id, refresh_session_state, set_session_cookie


router = APIRouter()


def recommendations_cache_key(user_id: str) -> str:
    return f"user:{user_id}:recomms"


def ensure_recommendation_user(user_id: str) -> None:
    # узел пользователя создаем заранее, для безопасного обновления графа
    run_query(
        """
        MERGE (:User {id: $user_id})
        """,
        {"user_id": user_id},
    )


def ensure_recommendation_event(event_id: str, title: str) -> None:
    run_query(
        """
        MERGE (event:Event {id: $event_id})
        SET event.title = $title
        """,
        {
            "event_id": event_id,
            "title": title,
        },
    )


def record_recommendation_like(user_id: str, event_id: str, title: str) -> None:
    # дизлайк не удаляет связь 
    run_query(
        """
        MERGE (user:User {id: $user_id})
        MERGE (event:Event {id: $event_id})
        SET event.title = $title
        MERGE (user)-[:LIKED]->(event)
        """,
        {
            "user_id": user_id,
            "event_id": event_id,
            "title": title,
        },
    )


def _read_cached_recommendations(user_id: str) -> list[dict[str, object]] | None:
    cached_events = read_json_hash_field(recommendations_cache_key(user_id), "events")
    if cached_events is None:
        return None

    if not isinstance(cached_events, list):
        return None

    return cached_events


def _write_cached_recommendations(user_id: str, events: list[dict[str, object]]) -> None:
    write_json_hash_field(recommendations_cache_key(user_id), "events", events, APP_RECOMMENDATIONS_TTL)


def _load_recommendation_candidates(user_id: str) -> list[dict[str, object]]:
    # ищем "похожих" пользователей через общие лайки и берем их события,
    # исключая уже лайкнутые event_id и любые события с тем же title.
    rows = run_query(
        """
        MATCH (user:User {id: $user_id})
        OPTIONAL MATCH (user)-[:LIKED]->(liked:Event)
        WITH user, collect(liked.id) AS liked_event_ids, collect(liked.title) AS liked_titles
        MATCH (user)-[:LIKED]->(:Event)<-[:LIKED]-(other:User)-[:LIKED]->(candidate:Event)
        WHERE other.id <> $user_id
          AND NOT candidate.id IN liked_event_ids
          AND NOT candidate.title IN liked_titles
        RETURN candidate.id AS event_id, count(DISTINCT other) AS score
        ORDER BY score DESC, event_id ASC
        """,
        {"user_id": user_id},
    )

    return rows


def _coerce_score(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _pick_nearest_event(documents: list[dict[str, object]]) -> dict[str, object]:
    # если у нескольких событий одинаковый title, вохвращаем ближайшее по started_at
    def started_at_sort_key(document: dict[str, object]) -> tuple[int, str]:
        started_at_raw = document.get("started_at")
        if not isinstance(started_at_raw, str):
            return (1, "")

        started_at = parse_rfc3339(started_at_raw)
        if started_at is None:
            return (1, started_at_raw)

        return (0, started_at.isoformat())

    return min(documents, key=started_at_sort_key)


def _build_recommendations_from_mongo(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    event_ids = [row["event_id"] for row in rows if isinstance(row.get("event_id"), str)]
    if not event_ids:
        return []

    parsed_event_ids = []
    for event_id in event_ids:
        parsed_event_id = parse_object_id(event_id)
        if parsed_event_id is not None:
            parsed_event_ids.append(parsed_event_id)

    if not parsed_event_ids:
        return []

    try:
        documents = list(events_collection.find({"_id": {"$in": parsed_event_ids}}))
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    documents_by_id = {str(document["_id"]): document for document in documents}
    documents_by_title: dict[str, list[dict[str, object]]] = defaultdict(list)
    scores_by_title: dict[str, int] = defaultdict(int)

    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            continue
        document = documents_by_id.get(event_id)
        if document is None:
            continue

        title = document.get("title")
        if not isinstance(title, str):
            continue

        # суммируем релевантность по title, потому что итоговая выдача тоже дедуплицируется по title
        documents_by_title[title].append(document)
        scores_by_title[title] += _coerce_score(row.get("score"))

    ranked_events: list[tuple[int, dict[str, object]]] = []
    for title, title_documents in documents_by_title.items():
        if not title_documents:
            continue
        ranked_events.append((scores_by_title[title], _pick_nearest_event(title_documents)))

    def ranking_key(item: tuple[int, dict[str, object]]) -> tuple[int, str, str]:
        started_at_raw = item[1].get("started_at")
        started_at = parse_rfc3339(started_at_raw) if isinstance(started_at_raw, str) else None
        return (
            -item[0],
            started_at.isoformat() if started_at is not None else str(started_at_raw or ""),
            str(item[1]["_id"]),
        )

    ranked_events.sort(key=ranking_key)

    return [serialize_event(document) for _, document in ranked_events]


def get_recommendations_for_user(user_id: str) -> list[dict[str, object]]:
    cached_events = _read_cached_recommendations(user_id)
    if cached_events is not None:
        return cached_events

    # при cache miss пересчитываем рекомендации из Neo4j + Mongo и сразу кладем готовый ответ в Redis
    rows = _load_recommendation_candidates(user_id)
    events = _build_recommendations_from_mongo(rows)
    _write_cached_recommendations(user_id, events)
    return events


@router.get("/recommendations")
def list_recommendations(request: Request) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    refresh_session_state(sid, user_id)
    response = JSONResponse(content={"events": get_recommendations_for_user(user_id)})
    set_session_cookie(response, sid)
    return response
