from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["OFFLINE_MODE"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{ROOT / 'data' / 'enriched' / 'test.db'}"

from src.graph import run_pipeline  # noqa: E402


def test_end_to_end_offline():
    state = run_pipeline(
        category="4K LED TV",
        slug="4k-led-tv",
        seed_source="croma",
        limit=3,
    )

    assert state.get("run_id")
    schema = state.get("category_schema")
    assert schema is not None
    assert len(schema.fields) >= 10

    enriched = state.get("enriched", [])
    assert len(enriched) == 3

    for p in enriched:
        assert p.product_id
        assert p.brand
        assert p.model
        assert p.coverage > 0.2, f"coverage too low: {p.coverage}"
        assert isinstance(p.fields, dict)
        assert len(p.fields) > 0


def test_reconciliation_provenance():
    state = run_pipeline(
        category="4K LED TV", slug="4k-led-tv", limit=2,
    )
    for p in state.get("enriched", []):
        for name, ef in p.fields.items():
            assert isinstance(ef.provenance, list)
            if ef.observations:
                assert ef.confidence >= 0.0
                assert ef.confidence <= 1.0
