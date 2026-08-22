"""FastAPI entrypoint. Run: uv run uvicorn app.main:app --port 8000"""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.sim import pool


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    pool.start_pool()
    yield
    pool.shutdown_pool()


app = FastAPI(title="AI Antenna Engineer", lifespan=lifespan)
app.add_middleware(  # hackathon posture: open CORS
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
