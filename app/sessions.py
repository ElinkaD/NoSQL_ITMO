import re
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.config import SESSION_TTL
from app.db import StorageUnavailableError, redis_cli, users_collection


router = APIRouter()

COOKIE_NAME = "X-Session-Id"
SID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# Lua-скрипт для атомарного создания сессии в Redis
CREATE_SESSION_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1], 'created_at', ARGV[1], 'updated_at', ARGV[1])
if ARGV[3] ~= '' then
  redis.call('HSET', KEYS[1], 'user_id', ARGV[3])
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def session_key(sid: str) -> str:
    return f"sid:{sid}"


def get_request_sid(request: Request) -> str | None:
    sid = request.cookies.get(COOKIE_NAME)
    return sid if sid and SID_PATTERN.fullmatch(sid) else None


def set_session_cookie(response: Response, sid: str) -> None:
    response.headers.append(
        "Set-Cookie",
        f"{COOKIE_NAME}={sid}; HttpOnly; Path=/; Max-Age={SESSION_TTL}",
    )


def clear_session_cookie(response: Response, sid: str = "") -> None:
    response.headers.append(
        "Set-Cookie",
        f"{COOKIE_NAME}={sid}; HttpOnly; Path=/; Max-Age=0",
    )


def session_exists(sid: str) -> bool:
    try:
        return bool(redis_cli.exists(session_key(sid)))
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def get_session_data(sid: str) -> dict[str, str]:
    # читает все поля сессии из Redis hash
    try:
        return redis_cli.hgetall(session_key(sid))
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def create_session(user_id: str | None = None) -> str:
    user_id_arg = user_id or ""

    # крутимся пока не создадим уникальную сессию
    while True: 
        sid = secrets.token_hex(16)
        try:
            created = redis_cli.eval(
                CREATE_SESSION_SCRIPT,
                1,
                session_key(sid),
                now_rfc3339(),
                SESSION_TTL,
                user_id_arg,
            )
        except RedisError as exc:
            raise StorageUnavailableError("redis") from exc

        if created:
            return sid


def refresh_session_state(sid: str, user_id: str | None = None) -> None:
    key = session_key(sid)
    mapping = {"updated_at": now_rfc3339()}
    if user_id is not None:
        mapping["user_id"] = user_id

    try:
        redis_cli.hset(key, mapping=mapping)
        redis_cli.expire(key, SESSION_TTL)
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def delete_session(sid: str) -> None:
    try:
        redis_cli.delete(session_key(sid))
    except RedisError as exc:
        raise StorageUnavailableError("redis") from exc


def get_active_sid(request: Request, *, suppress_errors: bool = False) -> str | None:
    sid = get_request_sid(request)
    if sid is None:
        return None

    try:
        return sid if session_exists(sid) else None
    except StorageUnavailableError:
        if suppress_errors:
            return None
        raise


def get_current_user_id(request: Request) -> tuple[str | None, str | None]:
    sid = get_active_sid(request)
    if sid is None:
        # нет сессии — нет пользователя
        return None, None

    # из Redis-даты сессии пытаемся достать user_id
    user_id = get_session_data(sid).get("user_id")
    if not user_id:
        # cессия есть, но пользователь не авторизован
        return sid, None

    try:
        # Проверяем, что user_id можно преобразовать в Mongo ObjectId
        user_object_id = ObjectId(user_id)
    except Exception:
        # считаем user_id невалидным
        return sid, None

    try:
        # Проверяем, что пользователь реально существует в MongoDB
        user = users_collection.find_one({"_id": user_object_id}, {"_id": 1})
    except PyMongoError as exc:
        raise StorageUnavailableError("mongodb") from exc

    if user is None:
        # В сессии user_id есть, но такого пользователя в базе уже нет
        return sid, None

    return sid, user_id


def invalid_field_response(
    field_name: str,
    sid: str | None = None,
    *,
    is_parameter: bool = False,
    refresh: bool = True,
) -> JSONResponse:
    suffix = "parameter" if is_parameter else "field"
    response = JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"message": f'invalid "{field_name}" {suffix}'},
    )
    if sid is not None:
        if refresh:
            refresh_session_state(sid)
        set_session_cookie(response, sid)
    return response


@router.get("/health")
def healthcheck(request: Request) -> JSONResponse:
    response = JSONResponse(content={"status": "ok"})
    if sid := get_active_sid(request, suppress_errors=True):
        set_session_cookie(response, sid)
    return response


@router.post("/session")
def upsert_session(request: Request) -> Response:
    # если у клиента уже есть активная сессия
    if sid := get_active_sid(request):
        refresh_session_state(sid)
        response = Response(status_code=status.HTTP_200_OK)
        set_session_cookie(response, sid)
        return response

    sid = create_session()
    response = Response(status_code=status.HTTP_201_CREATED)
    set_session_cookie(response, sid)
    return response
