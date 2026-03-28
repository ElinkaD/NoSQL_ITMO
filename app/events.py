import re

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.common import is_non_empty_string, parse_rfc3339, parse_uint_parameter
from app.db import StorageUnavailableError, events_collection
from app.sessions import (
    get_active_sid,
    get_current_user_id,
    invalid_field_response,
    now_rfc3339,
    refresh_session_state,
    set_session_cookie,
)


router = APIRouter()


@router.post("/events")
async def create_event(request: Request) -> Response:
    sid, user_id = get_current_user_id(request)
    # Если user_id нет, значит пользователь не авторизован
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("title", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("title", sid)

    # собираем обязательные поля события
    required_string_fields = {
        "title": payload.get("title"),
        "address": payload.get("address"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
    }
    for field_name, value in required_string_fields.items():
        if not is_non_empty_string(value):
            return invalid_field_response(field_name, sid)

    # распарсим поля ниже + проверка на корректность 
    started_at = parse_rfc3339(payload["started_at"])
    if started_at is None:
        return invalid_field_response("started_at", sid)

    finished_at = parse_rfc3339(payload["finished_at"])
    if finished_at is None or finished_at <= started_at:
        return invalid_field_response("finished_at", sid)

    # формируем вставку о событие в mongodb
    document = {
        "title": payload["title"],
        "location": {
            "address": payload["address"],
        },
        "created_at": now_rfc3339(),
        "created_by": user_id,
        "started_at": payload["started_at"],
        "finished_at": payload["finished_at"],
    }

    try:
        result = events_collection.insert_one(document)
    except DuplicateKeyError:
        response = JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "event already exists"},
        )
        refresh_session_state(sid, user_id)
        set_session_cookie(response, sid)
        return response
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    refresh_session_state(sid, user_id)
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"id": str(result.inserted_id)},
    )
    set_session_cookie(response, sid)
    return response


@router.get("/events")
def list_events(request: Request) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    title = request.query_params.get("title")
    raw_limit = request.query_params.get("limit")
    raw_offset = request.query_params.get("offset")

    limit = parse_uint_parameter(raw_limit)
    if raw_limit is not None and limit is None:
        return invalid_field_response("limit", sid, is_parameter=True, refresh=False)

    offset = parse_uint_parameter(raw_offset)
    if raw_offset is not None and offset is None:
        return invalid_field_response("offset", sid, is_parameter=True, refresh=False)

    mongo_filter: dict[str, object] = {}
    if title is not None:
        mongo_filter["title"] = {"$regex": re.escape(title)}

    try:
        # по умолчанию строим mongo запрос и сортируем по дате создания по убыванию, далее добавляем если были указаны limit и offset
        cursor = events_collection.find(mongo_filter).sort("created_at", DESCENDING)
        if offset is not None:
            cursor = cursor.skip(offset)
        if limit == 0:
            documents = []
        else:
            if limit is not None:
                cursor = cursor.limit(limit)
            documents = list(cursor)
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    # преобразуем MongoDB-документы в обычный JSON-ответ
    events = []
    for document in documents:
        events.append(
            {
                "id": str(document["_id"]),
                "title": document["title"],
                "location": document["location"],
                "created_at": document["created_at"],
                "created_by": document["created_by"],
                "started_at": document["started_at"],
                "finished_at": document["finished_at"],
            }
        )

    response = JSONResponse(content={"events": events, "count": len(events)})
    if sid is not None:
        set_session_cookie(response, sid)
    return response
