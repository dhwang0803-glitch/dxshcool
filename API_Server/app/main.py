from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, recommend, search, vod
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
app.include_router(vod.router, prefix="/vod", tags=["vod"])
app.include_router(recommend.router, prefix="/recommend", tags=["recommend"])
app.include_router(search.router, prefix="/similar", tags=["search"])


@app.get("/health")
async def health():
    return {"status": "ok"}
