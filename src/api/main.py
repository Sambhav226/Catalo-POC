from __future__ import annotations

import logging
import uuid
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import settings
from src.graph import run_pipeline
from src.storage import Repo

log = logging.getLogger("api")

app = FastAPI(
    title="Catalog Enrichment API",
    version="0.1.0",
    description="Agentic product catalog enrichment. See /docs for endpoints.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_repo = Repo()
_run_status: dict[str, str] = {}


class EnrichRequest(BaseModel):
    category: str
    slug: str | None = None
    seed_source: str = "croma"
    seed_urls: list[str] = []
    limit: int = 0


class EnrichResponse(BaseModel):
    run_id: str
    status: str


def _slugify(s: str) -> str:
    from slugify import slugify
    return slugify(s)


def _run_in_bg(run_id: str, category: str, slug: str, seed_source: str, urls: list[str], limit: int):
    _run_status[run_id] = "running"
    try:
        run_pipeline(
            category=category, slug=slug, seed_source=seed_source,
            seed_urls=urls, limit=limit, run_id=run_id,
        )
        _run_status[run_id] = "completed"
    except Exception as e:
        log.exception("run %s failed: %s", run_id, e)
        _run_status[run_id] = f"failed: {e}"


@app.post("/enrich", response_model=EnrichResponse)
def enrich(body: EnrichRequest):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    slug = body.slug or _slugify(body.category)
    _run_status[run_id] = "queued"
    Thread(
        target=_run_in_bg,
        args=(run_id, body.category, slug, body.seed_source, body.seed_urls, body.limit),
        daemon=True,
    ).start()
    return EnrichResponse(run_id=run_id, status="queued")


@app.get("/runs")
def list_runs(limit: int = 20):
    return _repo.list_runs(limit=limit)


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    live = _run_status.get(run_id)
    row = _repo.get_run(run_id)
    if not row and not live:
        raise HTTPException(status_code=404, detail="unknown run")
    return {**(row or {"id": run_id}), "live_status": live or "unknown"}


@app.get("/products/{run_id}")
def get_products(run_id: str):
    products = _repo.list_products(run_id)
    if not products:
        raise HTTPException(status_code=404, detail="no products for run")
    return products


@app.get("/schemas/{category}")
def get_schema(category: str):
    s = _repo.latest_schema(category)
    if not s:
        raise HTTPException(status_code=404, detail="no schema yet for this category")
    return s


@app.get("/healthz")
def healthz():
    return {"ok": True, "offline_mode": settings.is_offline()}
