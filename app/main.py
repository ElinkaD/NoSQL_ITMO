import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from redis import Redis


COOKIE_NAME = "X-Session-Id"
SID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SESSION_TTL = int(os.getenv("APP_USER_SESSION_TTL", "60"))
CREATE_SESSION_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1], 'created_at', ARGV[1], 'updated_at', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

app = FastAPI()
redis_cli = Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def session_key(sid: str) -> str:
    return f"sid:{sid}"


def get_sid(request: Request) -> str | None:
    sid = request.cookies.get(COOKIE_NAME)
    return sid if sid and SID_PATTERN.fullmatch(sid) else None


def session_exists(sid: str) -> bool:
    return bool(redis_cli.exists(session_key(sid)))


def set_session_cookie(response: Response, sid: str) -> None:
    response.headers.append(
        "Set-Cookie",
        f"{COOKIE_NAME}={sid}; HttpOnly; Path=/; Max-Age={SESSION_TTL}",
    )


def create_session() -> str:
    while True:
        sid = secrets.token_hex(16)
        if redis_cli.eval(CREATE_SESSION_SCRIPT, 1, session_key(sid), now_rfc3339(), SESSION_TTL):
            return sid


@app.get("/health")
def healthcheck(request: Request) -> JSONResponse:
    response = JSONResponse(content={"status": "ok"})
    if sid := get_sid(request):
        if session_exists(sid):
            set_session_cookie(response, sid)
    return response


def refresh_session(sid: str) -> Response:
    key = session_key(sid)
    redis_cli.hset(key, mapping={"updated_at": now_rfc3339()})
    redis_cli.expire(key, SESSION_TTL)
    response = Response(status_code=status.HTTP_200_OK)
    set_session_cookie(response, sid)
    return response


@app.post("/session")
def upsert_session(request: Request) -> Response:
    if sid := get_sid(request):
        if session_exists(sid):
            return refresh_session(sid)

    sid = create_session()
    response = Response(status_code=status.HTTP_201_CREATED)
    set_session_cookie(response, sid)
    return response
