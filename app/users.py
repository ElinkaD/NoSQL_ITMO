import re
from datetime import date

import bcrypt
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.common import (
    is_non_empty_string,
    is_valid_event_category,
    parse_optional_parameter,
    parse_non_empty_string_parameter,
    parse_object_id,
    parse_rfc3339,
    parse_yyyymmdd,
    parse_uint_parameter,
)
from app.db import StorageUnavailableError, events_collection, users_collection
from app.sessions import (
    clear_session_cookie,
    create_session,
    delete_session,
    get_active_sid,
    get_current_user_id,
    invalid_field_response,
    refresh_session_state,
    set_session_cookie,
)


router = APIRouter()


def serialize_user(document: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(document["_id"]),
        "full_name": document["full_name"],
        "username": document["username"],
    }


def serialize_event(document: dict[str, object]) -> dict[str, object]:
    event = {
        "id": str(document["_id"]),
        "title": document["title"],
        "location": dict(document["location"]),
        "created_at": document["created_at"],
        "created_by": document["created_by"],
        "started_at": document["started_at"],
        "finished_at": document["finished_at"],
    }

    if "category" in document:
        event["category"] = document["category"]
    if "price" in document:
        event["price"] = document["price"]
    if "description" in document:
        event["description"] = document["description"]

    return event


def user_not_found_response(sid: str | None) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Not found"},
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


def user_events_not_found_response(sid: str | None) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "User not found"},
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


def matches_started_date_range(
    document: dict[str, object],
    started_date_from: date | None,
    started_date_to: date | None,
) -> bool:
    started_at_raw = document.get("started_at")
    if not isinstance(started_at_raw, str):
        return False

    started_at = parse_rfc3339(started_at_raw)
    if started_at is None:
        return False

    started_at_date = started_at.date()
    if started_date_from is not None and started_at_date < started_date_from:
        return False
    if started_date_to is not None and started_at_date > started_date_to:
        return False
    return True


# регистрация нового пользователя
@router.post("/users")
async def create_user(request: Request) -> Response:
    sid = get_active_sid(request)

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("full_name", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("full_name", sid)

    for field_name in ("full_name", "username", "password"):
        if not is_non_empty_string(payload.get(field_name)):
            return invalid_field_response(field_name, sid)
    
    # хэшируем пароль для хранения
    password_hash = bcrypt.hashpw(payload["password"].encode(), bcrypt.gensalt()).decode()
    
    # формаирование вставки для mongodb
    document = { 
        "full_name": payload["full_name"],
        "username": payload["username"],
        "password_hash": password_hash,
    }
    try:
        result = users_collection.insert_one(document)
    except DuplicateKeyError:
        response = JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "user already exists"},
        )
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    # создание новой сесси, чтобы пользователь автоматически считался залогиненным после регистрации
    new_sid = create_session(str(result.inserted_id))
    if sid is not None:
        delete_session(sid)

    response = Response(status_code=status.HTTP_201_CREATED)
    set_session_cookie(response, new_sid)
    return response


@router.get("/users")
def list_users(request: Request) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    limit, invalid_limit = parse_optional_parameter(request.query_params.get("limit"), parse_uint_parameter)
    if invalid_limit:
        return invalid_field_response("limit", sid, is_parameter=True, refresh=False)

    offset, invalid_offset = parse_optional_parameter(request.query_params.get("offset"), parse_uint_parameter)
    if invalid_offset:
        return invalid_field_response("offset", sid, is_parameter=True, refresh=False)

    user_id = request.query_params.get("id")
    name = request.query_params.get("name")

    mongo_filter: dict[str, object] = {}

    if user_id is not None:
        parsed_user_id = parse_object_id(user_id)
        if parsed_user_id is None:
            return invalid_field_response("id", sid, is_parameter=True, refresh=False)
        mongo_filter["_id"] = parsed_user_id

    parsed_name = parse_non_empty_string_parameter(name)
    if name is not None and parsed_name is None:
        return invalid_field_response("name", sid, is_parameter=True, refresh=False)
    if parsed_name is not None:
        mongo_filter["full_name"] = {"$regex": re.escape(parsed_name)}

    try:
        # по умолчанию строим mongo запрос по пользователям и сортируем по имени
        documents = list(users_collection.find(mongo_filter).sort("full_name", DESCENDING))
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if offset is not None:
        documents = documents[offset:]
    if limit is not None:
        documents = documents[:limit]

    response = JSONResponse(
        content={"users": [serialize_user(document) for document in documents], "count": len(documents)}
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.get("/users/{user_id}")
def get_user(request: Request, user_id: str) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return user_not_found_response(sid)

    try:
        document = users_collection.find_one({"_id": parsed_user_id}, {"password_hash": 0})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return user_not_found_response(sid)

    response = JSONResponse(content=serialize_user(document))
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.get("/users/{user_id}/events")
def list_user_events(request: Request, user_id: str) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    limit, invalid_limit = parse_optional_parameter(request.query_params.get("limit"), parse_uint_parameter)
    if invalid_limit:
        return invalid_field_response("limit", sid, is_parameter=True, refresh=False)

    offset, invalid_offset = parse_optional_parameter(request.query_params.get("offset"), parse_uint_parameter)
    if invalid_offset:
        return invalid_field_response("offset", sid, is_parameter=True, refresh=False)

    started_date_from, invalid_date_from = parse_optional_parameter(
        request.query_params.get("date_from"), parse_yyyymmdd
    )
    if invalid_date_from:
        return invalid_field_response("date_from", sid, is_parameter=True, refresh=False)

    started_date_to, invalid_date_to = parse_optional_parameter(
        request.query_params.get("date_to"), parse_yyyymmdd
    )
    if invalid_date_to:
        return invalid_field_response("date_to", sid, is_parameter=True, refresh=False)

    if started_date_from is not None and started_date_to is not None and started_date_from > started_date_to:
        return invalid_field_response("date_to", sid, is_parameter=True, refresh=False)

    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return user_events_not_found_response(sid)

    try:
        user_document = users_collection.find_one({"_id": parsed_user_id}, {"_id": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if user_document is None:
        return user_events_not_found_response(sid)

    mongo_filter: dict[str, object] = {"created_by": str(parsed_user_id)}

    title = request.query_params.get("title")
    if title is not None:
        mongo_filter["title"] = {"$regex": re.escape(title)}

    event_id = request.query_params.get("id")
    if event_id is not None:
        parsed_event_id = parse_object_id(event_id)
        if parsed_event_id is None:
            return invalid_field_response("id", sid, is_parameter=True, refresh=False)
        mongo_filter["_id"] = parsed_event_id

    category = request.query_params.get("category")
    if category is not None:
        if not is_valid_event_category(category):
            return invalid_field_response("category", sid, is_parameter=True, refresh=False)
        mongo_filter["category"] = category

    price_from, invalid_price_from = parse_optional_parameter(
        request.query_params.get("price_from"), parse_uint_parameter
    )
    if invalid_price_from:
        return invalid_field_response("price_from", sid, is_parameter=True, refresh=False)

    price_to, invalid_price_to = parse_optional_parameter(
        request.query_params.get("price_to"), parse_uint_parameter
    )
    if invalid_price_to:
        return invalid_field_response("price_to", sid, is_parameter=True, refresh=False)

    if price_from is not None or price_to is not None:
        if price_from is not None and price_to is not None and price_from > price_to:
            return invalid_field_response("price_to", sid, is_parameter=True, refresh=False)

        price_filter: dict[str, int] = {}
        if price_from is not None:
            price_filter["$gte"] = price_from
        if price_to is not None:
            price_filter["$lte"] = price_to
        mongo_filter["price"] = price_filter

    city = request.query_params.get("city")
    if city is not None:
        if not is_non_empty_string(city):
            return invalid_field_response("city", sid, is_parameter=True, refresh=False)
        mongo_filter["location.city"] = city

    try:
        documents = list(events_collection.find(mongo_filter).sort("created_at", DESCENDING))
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if started_date_from is not None or started_date_to is not None:
        documents = [
            document
            for document in documents
            if matches_started_date_range(document, started_date_from, started_date_to)
        ]

    if offset is not None:
        documents = documents[offset:]
    if limit is not None:
        documents = documents[:limit]

    response = JSONResponse(
        content={"events": [serialize_event(document) for document in documents], "count": len(documents)}
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.post("/auth/login")
async def login(request: Request) -> Response:
    sid = get_active_sid(request)

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("username", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("username", sid)

    for field_name in ("username", "password"):
        if not is_non_empty_string(payload.get(field_name)):
            return invalid_field_response(field_name, sid)

    try:
        user = users_collection.find_one({"username": payload["username"]})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    # случаи провала входа - пользователь не найден или не правильный пароль
    if user is None or not bcrypt.checkpw(payload["password"].encode(), user["password_hash"].encode()):
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "invalid credentials"},
        )
        # продлеваем сессию
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    user_id = str(user["_id"])

    if sid is None:
        # сессии не было - создаем
        sid = create_session(user_id)
    else:
        # привязываем существующую к пользователю + обновляем TTL
        refresh_session_state(sid, user_id)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sid)
    return response

# при выходе просто удаляем сессию 
@router.post("/auth/logout")
def logout(request: Request) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    delete_session(sid)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, sid)
    return response
