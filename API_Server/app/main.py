import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import ad, auth, home, notification, purchase, recommend, reservation, search, series, similar, user, vod, wishlist
from app.services.db import close_pool, create_pool
from app.services.exceptions import APIError
from app.services.pg_listener import start_pg_listener
from app.services.progress_buffer import flush_progress
from app.services.reservation_checker import check_reservations

log = logging.getLogger(__name__)


async def _periodic_flush():
    """60초마다 heartbeat 버퍼를 DB에 일괄 저장."""
    while True:
        await asyncio.sleep(60)
        try:
            await flush_progress()
        except Exception:
            log.exception("flush_progress failed")


async def _periodic_reservation_check():
    """30초마다 도래한 시청예약 알림 전송."""
    while True:
        await asyncio.sleep(30)
        try:
            await check_reservations()
        except Exception:
            log.exception("check_reservations failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()

    # background tasks
    tasks = [
        asyncio.create_task(_periodic_flush()),
        asyncio.create_task(_periodic_reservation_check()),
    ]

    # PG LISTEN/NOTIFY (트리거 미생성 시 에러 방지)
    listener_conn = None
    try:
        listener_conn = await start_pg_listener()
    except Exception:
        log.warning("PG LISTEN startup skipped (triggers may not exist yet)")

    yield

    # shutdown
    for t in tasks:
        t.cancel()
    await flush_progress()  # 잔여 버퍼 최종 flush
    if listener_conn:
        await listener_conn.close()
    await close_pool()


app = FastAPI(
    title="VOD Recommendation API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )

_cors_origins = [
    "http://localhost:3000",
]
_extra = os.getenv("CORS_ORIGINS", "")  # 쉼표 구분: "https://a.run.app,https://b.run.app"
if _extra:
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ad.router, prefix="/ad", tags=["ad"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(home.router, prefix="/home", tags=["home"])
app.include_router(search.router, prefix="/vod", tags=["search"])
app.include_router(vod.router, prefix="/vod", tags=["vod"])
app.include_router(series.router, prefix="/series", tags=["series"])
app.include_router(user.router, prefix="/user", tags=["user"])
app.include_router(purchase.router, prefix="/purchases", tags=["purchase"])
app.include_router(wishlist.router, prefix="/wishlist", tags=["wishlist"])
app.include_router(recommend.router, prefix="/recommend", tags=["recommend"])
app.include_router(reservation.router, prefix="/reservations", tags=["reservation"])
app.include_router(similar.router, prefix="/similar", tags=["similar"])
app.include_router(notification.router, prefix="/user/me/notifications", tags=["notification"])


@app.get("/health")
async def health():
    return {"status": "ok"}
