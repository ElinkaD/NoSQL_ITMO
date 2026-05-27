import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.cache import delete_cache_key, read_hash, write_hash
from app.common import parse_include_values, parse_object_id, parse_optional_parameter, parse_uint_parameter
from app.config import APP_EVENT_REVIEWS_TTL
from app.db import (
    StorageUnavailableError,
    consistency_level,
    events_collection,
    get_cassandra_session,
)
from app.sessions import (
    get_active_sid,
    get_current_user_id,
    invalid_field_response,
    refresh_session_state,
    set_session_cookie,
)


router = APIRouter()

# агрегат по отзывам храним отдельно от списка самих отзывов
ZERO_REVIEWS_SUMMARY = {"count": 0, "rating": 0.0}

_insert_review_statement = None
_select_reviews_statement = None
_select_user_review_statement = None
_update_review_statement = None


def should_include_reviews(include_value: str | None) -> bool:
    return "reviews" in parse_include_values(include_value)


def empty_reviews_summary() -> dict[str, int | float]:
    return dict(ZERO_REVIEWS_SUMMARY)


def reviews_cache_key(title: str) -> str:
    title_hash = hashlib.md5(title.encode("utf-8")).hexdigest()
    return f"event:{title_hash}:reviews"


def round_rating(value: float) -> float:
    decimal_value = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(decimal_value)


def format_review_timestamp(value: object) -> str:
    if not isinstance(value, datetime):
        raise ValueError("review timestamp must be datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_review_comment(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 300


def validate_review_rating(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5


def invalidate_reviews_cache(title: str) -> None:
    delete_cache_key(reviews_cache_key(title))


def _prepare_statements() -> tuple[object, object, object, object]:
    global _insert_review_statement, _select_reviews_statement, _select_user_review_statement, _update_review_statement

    session = get_cassandra_session()

    # подготавливаем запросы один раз и дальше переиспользуем
    if _insert_review_statement is None:
        _insert_review_statement = session.prepare(
            """
            INSERT INTO event_reviews (event_id, created_by, id, rating, comment, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            IF NOT EXISTS
            """
        )
        _insert_review_statement.consistency_level = consistency_level

    if _select_reviews_statement is None:
        _select_reviews_statement = session.prepare(
            """
            SELECT id, event_id, comment, created_at, created_by, rating, updated_at
            FROM event_reviews
            WHERE event_id = ?
            """
        )
        _select_reviews_statement.consistency_level = consistency_level

    if _select_user_review_statement is None:
        _select_user_review_statement = session.prepare(
            """
            SELECT id, event_id, comment, created_at, created_by, rating, updated_at
            FROM event_reviews
            WHERE event_id = ? AND created_by = ?
            """
        )
        _select_user_review_statement.consistency_level = consistency_level

    if _update_review_statement is None:
        _update_review_statement = session.prepare(
            """
            UPDATE event_reviews
            SET rating = ?, comment = ?, updated_at = ?
            WHERE event_id = ? AND created_by = ?
            """
        )
        _update_review_statement.consistency_level = consistency_level

    return (
        _insert_review_statement,
        _select_reviews_statement,
        _select_user_review_statement,
        _update_review_statement,
    )


def serialize_review_row(row: object) -> dict[str, object]:
    return {
        "id": str(row.id),
        "event_id": row.event_id,
        "comment": row.comment,
        "created_at": format_review_timestamp(row.created_at),
        "created_by": row.created_by,
        "rating": int(row.rating),
        "updated_at": format_review_timestamp(row.updated_at),
    }


def create_review(event_id: str, user_id: str, comment: str, rating: int) -> str | None:
    insert_statement, _, _, _ = _prepare_statements()
    review_id = uuid4()
    timestamp = datetime.now(timezone.utc)

    try:
        result = get_cassandra_session().execute(
            insert_statement,
            (
                event_id,
                user_id,
                review_id,
                rating,
                comment,
                timestamp,
                timestamp,
            ),
        )
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc

    applied = getattr(result[0], "applied", False)
    if not applied:
        return None

    return str(review_id)


def list_event_reviews(event_id: str, limit: int | None, offset: int | None) -> list[dict[str, object]]:
    _, select_reviews_statement, _, _ = _prepare_statements()

    try:
        rows = list(get_cassandra_session().execute(select_reviews_statement, (event_id,)))
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc

    if offset is not None:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]

    # offset в cassandra нет, поэтому режем уже в приложении
    return [serialize_review_row(row) for row in rows]


def get_user_review(event_id: str, user_id: str) -> object | None:
    _, _, select_user_review_statement, _ = _prepare_statements()

    try:
        rows = list(get_cassandra_session().execute(select_user_review_statement, (event_id, user_id)))
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc

    return rows[0] if rows else None


def update_review(event_id: str, user_id: str, rating: int, comment: str) -> None:
    _, _, _, update_review_statement = _prepare_statements()

    try:
        get_cassandra_session().execute(
            update_review_statement,
            (
                rating,
                comment,
                datetime.now(timezone.utc),
                event_id,
                user_id,
            ),
        )
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc


def _read_cached_reviews_summary(title: str) -> dict[str, int | float] | None:
    cached_reviews = read_hash(reviews_cache_key(title))
    if not cached_reviews:
        return None

    count = cached_reviews.get("count")
    rating = cached_reviews.get("rating")
    try:
        parsed_count = int(count)
        parsed_rating = float(rating)
    except (TypeError, ValueError):
        invalidate_reviews_cache(title)
        return None

    return {"count": parsed_count, "rating": parsed_rating}


def _write_cached_reviews_summary(title: str, summary: dict[str, int | float]) -> None:
    write_hash(
        reviews_cache_key(title),
        mapping={
            "count": summary["count"],
            "rating": summary["rating"],
        },
        ttl=APP_EVENT_REVIEWS_TTL,
    )


def _build_reviews_summary(rows: list[object]) -> dict[str, int | float]:
    if not rows:
        return empty_reviews_summary()

    # рейтинг считаем как среднее по всем отзывам и округляем до десятых
    rating_sum = sum(int(row.rating) for row in rows)
    return {
        "count": len(rows),
        "rating": round_rating(rating_sum / len(rows)),
    }


def _load_reviews_summary_by_event_ids(event_ids: list[str]) -> dict[str, int | float]:
    if not event_ids:
        return empty_reviews_summary()

    _, select_reviews_statement, _, _ = _prepare_statements()
    rows: list[object] = []

    try:
        session = get_cassandra_session()
        for event_id in event_ids:
            rows.extend(session.execute(select_reviews_statement, (event_id,)))
    except Exception as exc:
        raise StorageUnavailableError("cassandra") from exc

    return _build_reviews_summary(rows)


def get_reviews_summary_by_titles(titles: list[str]) -> dict[str, dict[str, int | float]]:
    unique_titles = list(dict.fromkeys(titles))
    summary_by_title: dict[str, dict[str, int | float]] = {}
    missing_titles: list[str] = []

    for title in unique_titles:
        cached_summary = _read_cached_reviews_summary(title)
        if cached_summary is None:
            missing_titles.append(title)
            continue
        summary_by_title[title] = cached_summary

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
            # агрегируем отзывы по title через все события с одинаковым названием
            summary = _load_reviews_summary_by_event_ids(event_ids_by_title.get(title, []))
            summary_by_title[title] = summary
            _write_cached_reviews_summary(title, summary)

    return {title: summary_by_title.get(title, empty_reviews_summary()) for title in unique_titles}


def refresh_reviews_cache(title: str) -> dict[str, int | float]:
    try:
        related_documents = events_collection.find(
            {"title": title},
            {"_id": 1},
        )
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    event_ids = [str(document["_id"]) for document in related_documents]
    summary = _load_reviews_summary_by_event_ids(event_ids)
    _write_cached_reviews_summary(title, summary)
    return summary


def review_not_found_response(sid: str | None, user_id: str | None = None) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Event not found"},
    )
    if sid is not None:
        if user_id is not None:
            refresh_session_state(sid, user_id)
        else:
            refresh_session_state(sid)
        set_session_cookie(response, sid)
    return response


@router.post("/events/{event_id}/reviews")
async def create_event_review(request: Request, event_id: str) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return review_not_found_response(sid, user_id)

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("comment", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("comment", sid)

    comment = payload.get("comment")
    if not validate_review_comment(comment):
        return invalid_field_response("comment", sid)

    rating = payload.get("rating")
    if not validate_review_rating(rating):
        return invalid_field_response("rating", sid)

    try:
        document = events_collection.find_one({"_id": parsed_event_id}, {"title": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return review_not_found_response(sid, user_id)

    # один пользователь может оставить только один отзыв на событие
    review_id = create_review(event_id, user_id, comment, rating)
    if review_id is None:
        response = JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "Already exists"},
        )
        refresh_session_state(sid, user_id)
        set_session_cookie(response, sid)
        return response

    refresh_reviews_cache(document["title"])

    refresh_session_state(sid, user_id)
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"id": review_id},
    )
    set_session_cookie(response, sid)
    return response


@router.get("/events/{event_id}/reviews")
def get_event_reviews(request: Request, event_id: str) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    limit, invalid_limit = parse_optional_parameter(request.query_params.get("limit"), parse_uint_parameter)
    if invalid_limit:
        return invalid_field_response("limit", sid, is_parameter=True, refresh=False)

    offset, invalid_offset = parse_optional_parameter(request.query_params.get("offset"), parse_uint_parameter)
    if invalid_offset:
        return invalid_field_response("offset", sid, is_parameter=True, refresh=False)

    # count здесь соответствует количеству элементов в текущем ответе после limit/offset
    reviews = list_event_reviews(event_id, limit, offset)
    response = JSONResponse(content={"reviews": reviews, "count": len(reviews)})
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.patch("/events/{event_id}/reviews/{review_id}")
async def patch_event_review(request: Request, event_id: str, review_id: str) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return review_not_found_response(sid, user_id)

    try:
        parsed_review_id = UUID(review_id)
    except ValueError:
        return review_not_found_response(sid, user_id)

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("rating", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("rating", sid)

    try:
        document = events_collection.find_one({"_id": parsed_event_id}, {"title": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return review_not_found_response(sid, user_id)

    # редактировать можно только свой отзыв, поэтому ищем его по event_id + user_id
    existing_review = get_user_review(event_id, user_id)
    if existing_review is None or existing_review.id != parsed_review_id:
        return review_not_found_response(sid, user_id)

    rating = int(existing_review.rating)
    if "rating" in payload:
        if not validate_review_rating(payload["rating"]):
            return invalid_field_response("rating", sid)
        rating = payload["rating"]

    comment = existing_review.comment
    if "comment" in payload:
        if not validate_review_comment(payload["comment"]):
            return invalid_field_response("comment", sid)
        comment = payload["comment"]

    update_review(event_id, user_id, rating, comment)
    refresh_reviews_cache(document["title"])

    refresh_session_state(sid, user_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sid)
    return response
