import bcrypt
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.common import is_non_empty_string
from app.db import StorageUnavailableError, users_collection
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
