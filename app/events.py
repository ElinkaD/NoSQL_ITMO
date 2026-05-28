import re
from datetime import date

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from app.common import (
    is_non_empty_string,
    is_valid_event_category,
    parse_optional_parameter,
    parse_object_id,
    parse_rfc3339,
    parse_yyyymmdd,
    parse_uint_parameter,
)
from app.db import StorageUnavailableError, events_collection, users_collection
from app.event_serializers import serialize_event
from app.recommendations import ensure_recommendation_event, record_recommendation_like
from app.reactions import (
    empty_reactions,
    get_reactions_by_titles,
    refresh_reactions_cache,
    should_include_reactions,
    upsert_event_reaction,
)
from app.reviews import empty_reviews_summary, get_reviews_summary_by_titles, should_include_reviews
from app.sessions import (
    get_active_sid,
    get_current_user_id,
    invalid_field_response,
    now_rfc3339,
    refresh_session_state,
    set_session_cookie,
)


router = APIRouter()


def event_not_found_response(sid: str | None) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Not found"},
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


def event_patch_not_found_response(sid: str | None, user_id: str | None = None) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Not found. Be sure that event exists and you are the organizer"},
    )
    if sid is not None:
        if user_id is not None:
            refresh_session_state(sid, user_id)
        else:
            refresh_session_state(sid)
        set_session_cookie(response, sid)
    return response


def event_reaction_not_found_response(sid: str | None, user_id: str | None = None) -> JSONResponse:
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


def build_event_filter(request: Request, sid: str | None) -> tuple[dict[str, object] | None, Response | None]:
    query_params = request.query_params
    mongo_filter: dict[str, object] = {}

    title = query_params.get("title")
    if title is not None:
        mongo_filter["title"] = {"$regex": re.escape(title)}

    event_id = query_params.get("id")
    if event_id is not None:
        parsed_event_id = parse_object_id(event_id)
        if parsed_event_id is None:
            return None, invalid_field_response("id", sid, is_parameter=True, refresh=False)
        mongo_filter["_id"] = parsed_event_id

    category = query_params.get("category")
    if category is not None:
        if not is_valid_event_category(category):
            return None, invalid_field_response("category", sid, is_parameter=True, refresh=False)
        mongo_filter["category"] = category

    price_from, invalid_price_from = parse_optional_parameter(
        query_params.get("price_from"), parse_uint_parameter
    )
    if invalid_price_from:
        return None, invalid_field_response("price_from", sid, is_parameter=True, refresh=False)

    price_to, invalid_price_to = parse_optional_parameter(
        query_params.get("price_to"), parse_uint_parameter
    )
    if invalid_price_to:
        return None, invalid_field_response("price_to", sid, is_parameter=True, refresh=False)

    if price_from is not None or price_to is not None:
        if price_from is not None and price_to is not None and price_from > price_to:
            return None, invalid_field_response("price_to", sid, is_parameter=True, refresh=False)

        price_filter: dict[str, int] = {}
        if price_from is not None:
            price_filter["$gte"] = price_from
        if price_to is not None:
            price_filter["$lte"] = price_to
        mongo_filter["price"] = price_filter

    city = query_params.get("city")
    if city is not None:
        if not is_non_empty_string(city):
            return None, invalid_field_response("city", sid, is_parameter=True, refresh=False)
        mongo_filter["location.city"] = city

    user = query_params.get("user")
    if user is not None:
        if not is_non_empty_string(user):
            return None, invalid_field_response("user", sid, is_parameter=True, refresh=False)
        try:
            user_document = users_collection.find_one({"username": user}, {"_id": 1})
        except PyMongoError as exc:
            raise StorageUnavailableError("mongodb") from exc

        # если пользователя нет то mongo запрос все равно можно выполнить но он гарантированно вернет пусто
        mongo_filter["created_by"] = str(user_document["_id"]) if user_document is not None else "__missing_user__"

    return mongo_filter, None


@router.post("/events")
async def create_event(request: Request) -> Response:
    sid, user_id = get_current_user_id(request)
    # если user_id нет значит пользователь не авторизован
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

    category = payload.get("category")
    if category is not None and not is_valid_event_category(category):
        return invalid_field_response("category", sid)

    price = payload.get("price")
    if price is not None and (not isinstance(price, int) or isinstance(price, bool) or price < 0):
        return invalid_field_response("price", sid)

    description = payload.get("description")
    if description is not None and not is_non_empty_string(description):
        return invalid_field_response("description", sid)

    city = payload.get("city")
    if city is not None and not is_non_empty_string(city):
        return invalid_field_response("city", sid)

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
    if category is not None:
        document["category"] = category
    if price is not None:
        document["price"] = price
    if description is not None:
        document["description"] = description
    if city is not None:
        document["location"]["city"] = city

    try:
        result = events_collection.insert_one(document)
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    ensure_recommendation_event(str(result.inserted_id), document["title"])
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

    mongo_filter, error_response = build_event_filter(request, sid)
    if error_response is not None:
        return error_response

    try:
        # сначала фильтруем по тем полям которые удобно и дешево отдать mongo
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

    include_reactions = should_include_reactions(request.query_params.get("include"))
    include_reviews = should_include_reviews(request.query_params.get("include"))
    serialized_events = [serialize_event(document) for document in documents]
    if include_reactions and serialized_events:
        reactions_by_title = get_reactions_by_titles([event["title"] for event in serialized_events])
        for event in serialized_events:
            event["reactions"] = reactions_by_title.get(event["title"], empty_reactions())
    elif include_reactions:
        for event in serialized_events:
            event["reactions"] = empty_reactions()

    if include_reviews and serialized_events:
        reviews_by_title = get_reviews_summary_by_titles([event["title"] for event in serialized_events])
        for event in serialized_events:
            event["reviews"] = reviews_by_title.get(event["title"], empty_reviews_summary())
    elif include_reviews:
        for event in serialized_events:
            event["reviews"] = empty_reviews_summary()

    response = JSONResponse(
        content={"events": serialized_events, "count": len(documents)}
    )
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.get("/events/{event_id}")
def get_event(request: Request, event_id: str) -> JSONResponse:
    sid = get_active_sid(request, suppress_errors=True)
    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return event_not_found_response(sid)

    try:
        document = events_collection.find_one({"_id": parsed_event_id})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return event_not_found_response(sid)

    event = serialize_event(document)
    if should_include_reactions(request.query_params.get("include")):
        event["reactions"] = get_reactions_by_titles([event["title"]]).get(event["title"], empty_reactions())
    if should_include_reviews(request.query_params.get("include")):
        event["reviews"] = get_reviews_summary_by_titles([event["title"]]).get(event["title"], empty_reviews_summary())

    response = JSONResponse(content=event)
    if sid is not None:
        set_session_cookie(response, sid)
    return response


@router.patch("/events/{event_id}")
async def patch_event(request: Request, event_id: str) -> Response:
    sid, user_id = get_current_user_id(request)
    # права на редактирование есть только у автора события
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return event_patch_not_found_response(sid, user_id)

    try:
        payload = await request.json()
    except Exception:
        return invalid_field_response("category", sid)
    if not isinstance(payload, dict):
        return invalid_field_response("category", sid)

    update_set: dict[str, object] = {}
    update_unset: dict[str, str] = {}

    if "category" in payload:
        category = payload["category"]
        if not is_valid_event_category(category):
            return invalid_field_response("category", sid)
        update_set["category"] = category

    if "price" in payload:
        price = payload["price"]
        if not isinstance(price, int) or isinstance(price, bool) or price < 0:
            return invalid_field_response("price", sid)
        update_set["price"] = price

    if "city" in payload:
        city = payload["city"]
        if not isinstance(city, str):
            return invalid_field_response("city", sid)
        if city == "":
            update_unset["location.city"] = ""
        elif is_non_empty_string(city):
            update_set["location.city"] = city
        else:
            return invalid_field_response("city", sid)

    update_query: dict[str, object] = {}
    if update_set:
        update_query["$set"] = update_set
    if update_unset:
        update_query["$unset"] = update_unset

    try:
        if update_query:
            result = events_collection.update_one(
                {"_id": parsed_event_id, "created_by": user_id},
                update_query,
            )
            if result.matched_count == 0:
                return event_patch_not_found_response(sid, user_id)
        else:
            document = events_collection.find_one({"_id": parsed_event_id, "created_by": user_id}, {"_id": 1})
            if document is None:
                return event_patch_not_found_response(sid, user_id)
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    refresh_session_state(sid, user_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sid)
    return response


@router.post("/events/{event_id}/like")
@router.post("/event/{event_id}/like")
def like_event(request: Request, event_id: str) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return event_reaction_not_found_response(sid, user_id)

    try:
        document = events_collection.find_one({"_id": parsed_event_id}, {"title": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return event_reaction_not_found_response(sid, user_id)

    upsert_event_reaction(event_id, user_id, 1)
    record_recommendation_like(user_id, event_id, document["title"])
    refresh_reactions_cache(document["title"])

    refresh_session_state(sid, user_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sid)
    return response


@router.post("/events/{event_id}/dislike")
@router.post("/event/{event_id}/dislike")
def dislike_event(request: Request, event_id: str) -> Response:
    sid, user_id = get_current_user_id(request)
    if user_id is None:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if sid is not None:
            refresh_session_state(sid)
            set_session_cookie(response, sid)
        return response

    parsed_event_id = parse_object_id(event_id)
    if parsed_event_id is None:
        return event_reaction_not_found_response(sid, user_id)

    try:
        document = events_collection.find_one({"_id": parsed_event_id}, {"title": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if document is None:
        return event_reaction_not_found_response(sid, user_id)

    upsert_event_reaction(event_id, user_id, -1)
    refresh_reactions_cache(document["title"])

    refresh_session_state(sid, user_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sid)
    return response
