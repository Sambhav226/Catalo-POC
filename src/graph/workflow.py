from __future__ import annotations

import logging
import time
import uuid

from langgraph.graph import StateGraph, END

from src.agents import (
    ScraperAgent, SchemaAgent, EnrichmentAgent,
    ReconciliationAgent, ValidatorAgent,
)
from src.models import PipelineState

log = logging.getLogger("graph")


def _persist_node(state: PipelineState) -> dict:
    from src.storage.repo import Repo
    repo = Repo()
    repo.save_pipeline_output(state)
    return {}


def build_graph():
    scraper = ScraperAgent()
    schema = SchemaAgent()
    enricher = EnrichmentAgent()
    reconciler = ReconciliationAgent()
    validator = ValidatorAgent()

    g = StateGraph(PipelineState)
    g.add_node("scrape", scraper.run)
    g.add_node("induce_schema", schema.run)
    g.add_node("enrich", enricher.run)
    g.add_node("reconcile", reconciler.run)
    g.add_node("validate", validator.run)
    g.add_node("persist", _persist_node)

    g.set_entry_point("scrape")
    g.add_edge("scrape", "induce_schema")
    g.add_edge("induce_schema", "enrich")
    g.add_edge("enrich", "reconcile")
    g.add_edge("reconcile", "validate")
    g.add_edge("validate", "persist")
    g.add_edge("persist", END)

    return g.compile()


def run_pipeline(
    category: str,
    slug: str,
    seed_source: str = "croma",
    seed_urls: list[str] | None = None,
    limit: int = 0,
    run_id: str | None = None,
) -> PipelineState:
    run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
    initial: PipelineState = {
        "run_id": run_id,
        "category": category,
        "slug": slug,
        "seed_source": seed_source,
        "seed_urls": seed_urls or [],
        "limit": limit,
        "errors": [],
        "stats": {},
    }
    graph = build_graph()
    t0 = time.time()
    final: PipelineState = graph.invoke(initial)  # type: ignore
    final.setdefault("stats", {})["elapsed_seconds"] = round(time.time() - t0, 2)
    return final
