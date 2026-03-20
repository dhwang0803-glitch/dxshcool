from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, home, purchase, recommend, series, similar, user, vod, wishlist
from app.services.db import close_pool, create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()


app = FastAPI(
    title="VOD Recommendation API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(home.router, prefix="/home", tags=["home"])
app.include_router(vod.router, prefix="/vod", tags=["vod"])
app.include_router(series.router, prefix="/series", tags=["series"])
app.include_router(user.router, prefix="/user", tags=["user"])
app.include_router(purchase.router, prefix="/purchases", tags=["purchase"])
app.include_router(wishlist.router, prefix="/wishlist", tags=["wishlist"])
app.include_router(recommend.router, prefix="/recommend", tags=["recommend"])
app.include_router(similar.router, prefix="/similar", tags=["similar"])


@app.get("/health")
async def health():
    return {"status": "ok"}
