from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from src.config import settings
from src.models import CategorySchema, SchemaField, PipelineState
from src.tools import LLMClient

log = logging.getLogger("agent.schema")


SCHEMA_SYSTEM = (
    "You are a product data architect. Given raw attribute names observed on multiple e-commerce "
    "and manufacturer pages for a single leaf category, produce a canonical, normalised JSON "
    "schema for that category. Merge synonymous attributes (e.g. 'Screen Size', 'Display Size', "
    "'Screen size (inch)' become one field). Choose safe dtypes. Add sensible enum values when "
    "the domain is discrete. Prefer snake_case field names."
)


class SchemaAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def run(self, state: PipelineState) -> dict:
        raw_pages = state.get("raw_pages", [])
        category = state.get("category", "Unknown")
        slug = state.get("slug") or ""

        observed = _collect_attributes(raw_pages)
        template = _load_template(slug)

        user_prompt = _build_user_prompt(category, slug, observed, template)

        try:
            result = self.llm.structured_call(
                system=SCHEMA_SYSTEM,
                user=user_prompt,
                response_model=CategorySchema,
            )
        except Exception as e:
            log.warning("schema induction failed, falling back to template: %s", e)
            result = _schema_from_template(category, template)

        if result and result.fields:
            result.induced_from = list({p.source for p in raw_pages})
            log.info("schema: induced %d fields from sources: %s", len(result.fields), result.induced_from)
            return {"category_schema": result}

        log.warning("schema induction returned empty, using template fallback")
        return {"category_schema": _schema_from_template(category, template)}


def _collect_attributes(pages) -> list[tuple[str, int]]:
    c: Counter[str] = Counter()
    for p in pages:
        for k in (p.raw_specs or {}).keys():
            c[k] += 1
    return c.most_common(60)


def _load_template(slug: str) -> dict:
    if not slug:
        return {}
    path = Path(settings.seed_dir) / "schemas" / f"{slug}.template.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_user_prompt(category: str, slug: str, observed: list[tuple[str, int]], template: dict) -> str:
    obs_str = "\n".join(f"  - {name}  (seen in {count} pages)" for name, count in observed)
    template_str = json.dumps(template, indent=2) if template else "(none)"
    return (
        f"CATEGORY = {category}\n"
        f"SLUG = {slug}\n\n"
        f"OBSERVED_ATTRIBUTES:\n{obs_str}\n\n"
        f"HINT_TEMPLATE:\n{template_str}\n\n"
        "Produce a CategorySchema with `category`, `version`, and `fields` (list of SchemaField). "
        "Aim for 20-35 fields. Mark truly essential ones as required=true."
    )


def _schema_from_template(category: str, template: dict) -> CategorySchema:
    if not template or "fields" not in template:
        return CategorySchema(category=category, fields=[
            SchemaField(name="brand", dtype="string", required=True),
            SchemaField(name="model_number", dtype="string", required=True),
            SchemaField(name="title", dtype="string", required=True),
        ])
    fields = [SchemaField(**f) for f in template["fields"]]
    return CategorySchema(category=category, fields=fields, induced_from=["template_fallback"])
