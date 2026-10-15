"""Data quality assistant API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.routers.quality import router
from app.seed import seed_if_needed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if get_settings().seed_demo_data:
        with SessionLocal() as session:
            seed_if_needed(session)
    yield


app = FastAPI(title="Data Quality Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "data-quality-assistant",
        "ui": "http://localhost:3000",
        "docs": "/docs",
    }
