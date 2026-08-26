from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.config import settings
from src.models import CategorySchema, SchemaField, EnrichedProduct, EnrichedField, PipelineState

log = logging.getLogger("agent.validator")


class ValidatorAgent:
    def run(self, state: PipelineState) -> dict:
        enriched: list[EnrichedProduct] = state.get("enriched", [])
        schema: CategorySchema = state.get("category_schema")
        slug = state.get("slug") or ""

        if not enriched or not schema:
            return {"enriched": enriched}

        rules = _load_rules(slug)
        by_name = schema.by_name()

        for prod in enriched:
            for field_name, ef in list(prod.fields.items()):
                sfield = by_name.get(field_name)
                if not sfield:
                    ef.flags.append("unknown_field")
                    continue
                ok, coerced, reason = _validate(sfield, ef.value)
                ef.value = coerced
                ef.validated = ok
                if not ok:
                    ef.flags.append(reason)

            self._apply_cross_rules(prod, rules)

            filled = sum(1 for f in prod.fields.values() if f.value not in (None, "", []))
            total = max(1, len(schema.fields))
            prod.coverage = round(filled / total, 3)

        return {"enriched": enriched}

    def _apply_cross_rules(self, prod: EnrichedProduct, rules: dict) -> None:
        for rule in rules.get("cross_field_rules", []):
            when = rule.get("when", {})
            when_contains = rule.get("when_contains", {})
            then = rule.get("then", {})
            then_required = rule.get("then_field_required")

            if when and not _match_when(prod, when):
                continue
            if when_contains and not _match_when_contains(prod, when_contains):
                continue

            for k, v in then.items():
                if k not in prod.fields or prod.fields[k].value in (None, ""):
                    prod.fields[k] = EnrichedField(
                        value=v,
                        confidence=0.6,
                        provenance=["cross_field_rule"],
                        observations=[],
                        flags=["derived"],
                    )

            if then_required and (
                then_required not in prod.fields
                or prod.fields[then_required].value in (None, "")
            ):
                prod.flags.append(f"missing_required:{then_required}")


def _match_when(prod: EnrichedProduct, when: dict) -> bool:
    for k, v in when.items():
        if k not in prod.fields:
            return False
        actual = prod.fields[k].value
        if str(actual).strip().lower() != str(v).strip().lower():
            return False
    return True


def _match_when_contains(prod: EnrichedProduct, when_contains: dict) -> bool:
    for k, v in when_contains.items():
        if k not in prod.fields:
            return False
        actual = str(prod.fields[k].value or "").lower()
        if str(v).lower() not in actual:
            return False
    return True


def _load_rules(slug: str) -> dict:
    if not slug:
        return {}
    path = Path(settings.seed_dir) / "schemas" / f"{slug}.rules.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(field: SchemaField, value: Any) -> tuple[bool, Any, str]:
    if value in (None, ""):
        if field.required:
            return False, value, "missing_required"
        return True, value, ""

    coerced = _coerce(field, value)
    if coerced is None:
        return False, value, f"type_coerce_failed:{field.dtype}"

    if field.dtype in {"int", "float"}:
        if field.min is not None and coerced < field.min:
            return False, coerced, f"below_min:{field.min}"
        if field.max is not None and coerced > field.max:
            return False, coerced, f"above_max:{field.max}"

    if field.dtype == "enum" and field.enum_values:
        if coerced not in field.enum_values and str(coerced) not in [str(e) for e in field.enum_values]:
            return False, coerced, "enum_mismatch"

    return True, coerced, ""


def _coerce(field: SchemaField, value: Any) -> Any:
    if field.dtype == "int":
        try:
            m = re.search(r"-?\d+", str(value))
            return int(m.group(0)) if m else None
        except Exception:
            return None
    if field.dtype == "float":
        try:
            m = re.search(r"-?\d+(?:\.\d+)?", str(value))
            return float(m.group(0)) if m else None
        except Exception:
            return None
    if field.dtype == "bool":
        s = str(value).strip().lower()
        if s in {"true", "yes", "1", "y"}:
            return True
        if s in {"false", "no", "0", "n"}:
            return False
        return bool(value)
    if field.dtype == "enum":
        return str(value).strip()
    return str(value).strip()
