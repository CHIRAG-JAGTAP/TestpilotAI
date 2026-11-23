"""Minimal Phase-1 entry point (routers arrive in later phases)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tests_router import router as tests_router

from app.core.config import get_settings
from app.database import maintenance as mt
from app.database.init_db import init_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()          # migrate (with pre-migration backup) before serving
    yield


app = FastAPI(title="TestPilot", version="0.1.0", lifespan=lifespan,
              description="Execution- and Coverage-Guided Refinement of Python Unit Tests")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(tests_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/health/database")
def database_health() -> dict:
    s = get_settings()
    return mt.database_health(s.db_path, s.backup_dir)
