from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from src.config import settings
from src.models import (
    CategorySchema, EnrichedProduct, EnrichedField, FieldObservation, PipelineState,
)

log = logging.getLogger("agent.reconciliation")


class ReconciliationAgent:
    def run(self, state: PipelineState) -> dict:
        enriched: list[EnrichedProduct] = state.get("enriched", [])
        schema: CategorySchema = state.get("category_schema")
        if not enriched or not schema:
            return {"enriched": enriched}

        for prod in enriched:
            for field, ef in prod.fields.items():
                if not ef.observations:
                    continue
                winner, confidence = _pick_winner(ef.observations)
                ef.value = winner.value
                ef.confidence = confidence
                ef.provenance = [o.source_url for o in ef.observations]

            filled = sum(1 for f in prod.fields.values() if f.value not in (None, "", []))
            total = max(1, len(schema.fields))
            prod.coverage = round(filled / total, 3)

        return {"enriched": enriched}


def _pick_winner(observations: list[FieldObservation]) -> tuple[FieldObservation, float]:
    scored = [
        (o, settings.trust_weights.get(o.source_type, 0.5) * o.intrinsic_confidence, o)
        for o in observations
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    winner, top_score, _ = scored[0]

    canon_winner = _canonical(winner.value)
    agree = sum(1 for o in observations if _canonical(o.value) == canon_winner)
    total = len(observations)

    confidence = round(min(1.0, top_score * (agree / total) * (1.0 + 0.1 * (total - 1))), 3)
    return winner, confidence


def _canonical(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().lower().replace(" ", "").replace('"', "").replace("'", "")
