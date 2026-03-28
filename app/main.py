from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.db import StorageUnavailableError, ensure_indexes
from app.events import router as events_router
from app.sessions import router as sessions_router
from app.users import router as users_router


app = FastAPI()
app.include_router(sessions_router)
app.include_router(users_router)
app.include_router(events_router)


@app.on_event("startup")
def startup() -> None:
    ensure_indexes()


@app.exception_handler(StorageUnavailableError)
def handle_storage_unavailable(_: Request, exc: StorageUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"message": f"{exc.storage_name} unavailable"},
    )


@app.exception_handler(RedisError)
def handle_redis_error(_: Request, __: RedisError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"message": "redis unavailable"},
    )


@app.exception_handler(PyMongoError)
def handle_mongo_error(_: Request, __: PyMongoError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"message": "mongodb unavailable"},
    )
