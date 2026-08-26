from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload

from src.config import settings
from src.models import (
    PipelineState, CategorySchema as PdCategorySchema,
    EnrichedProduct as PdEnrichedProduct, Product as PdProduct,
    RawProductPage as PdRawProductPage,
)
from src.storage.models import (
    Base, Run, SchemaRow, ProductRow, ProductPageRow, EnrichedProductRow,
)

log = logging.getLogger("storage")


class Repo:
    _engine = None

    def __init__(self):
        if Repo._engine is None:
            Path(settings.enriched_dir).mkdir(parents=True, exist_ok=True)
            Repo._engine = create_engine(settings.database_url, future=True)
            Base.metadata.create_all(Repo._engine)

    def save_pipeline_output(self, state: PipelineState) -> None:
        run_id: str = state.get("run_id") or f"run-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        category: str = state.get("category", "")
        slug: str = state.get("slug") or ""
        schema_pd: PdCategorySchema | None = state.get("category_schema")
        products_pd: list[PdProduct] = state.get("products") or []
        enriched_pd: list[PdEnrichedProduct] = state.get("enriched") or []
        stats: dict = state.get("stats") or {}

        with Session(Repo._engine) as s:
            schema_row = self._insert_schema(s, slug, category, schema_pd) if schema_pd else None

            run = s.get(Run, run_id) or Run(id=run_id)
            run.category = category
            run.slug = slug
            run.schema_id = schema_row.id if schema_row else None
            run.status = "completed"
            run.seed_source = state.get("seed_source")
            run.started_at = run.started_at or datetime.utcnow()
            run.finished_at = datetime.utcnow()
            run.stats = stats
            s.merge(run)

            product_row_map: dict[str, ProductRow] = {}
            for pp in products_pd:
                prod = self._upsert_product(s, slug, category, pp)
                product_row_map[pp.product_id] = prod
                for page in pp.pages:
                    self._upsert_page(s, prod, page)

            s.flush()

            for ep in enriched_pd:
                product = product_row_map.get(ep.product_id) or self._upsert_product_lite(s, slug, category, ep)
                s.add(EnrichedProductRow(
                    run_id=run.id,
                    product_id=product.id,
                    coverage=ep.coverage,
                    seed_source=ep.seed_source,
                    seed_url=ep.seed_url,
                    fields_json=_serialize_fields(ep),
                    flags_json=ep.flags or [],
                ))

            s.commit()

        self._write_snapshot(run_id, category, slug, stats, schema_pd, enriched_pd)
        log.info("saved run %s to db + json snapshot", run_id)

    def _insert_schema(self, s: Session, slug: str, category: str, schema_pd: PdCategorySchema) -> SchemaRow:
        s.execute(
            SchemaRow.__table__.update()
            .where(SchemaRow.slug == slug)
            .values(is_active=False)
        )
        row = SchemaRow(
            slug=slug or _slugify(category),
            category=category,
            version=schema_pd.version,
            fields_json=[json.loads(f.model_dump_json()) for f in schema_pd.fields],
            induced_from=list(schema_pd.induced_from or []),
            is_active=True,
        )
        s.add(row)
        s.flush()
        return row

    def _upsert_product(self, s: Session, slug: str, category: str, pp: PdProduct) -> ProductRow:
        row = s.execute(
            select(ProductRow).where(ProductRow.slug == slug, ProductRow.external_id == pp.product_id)
        ).scalar_one_or_none()
        if row:
            if pp.brand and row.brand != pp.brand:
                row.brand = pp.brand
            if pp.model and row.model != pp.model:
                row.model = pp.model
            return row
        row = ProductRow(
            slug=slug or _slugify(category),
            category=category,
            external_id=pp.product_id,
            brand=pp.brand,
            model=pp.model,
        )
        s.add(row)
        s.flush()
        return row

    def _upsert_product_lite(self, s: Session, slug: str, category: str, ep: PdEnrichedProduct) -> ProductRow:
        row = s.execute(
            select(ProductRow).where(ProductRow.slug == slug, ProductRow.external_id == ep.product_id)
        ).scalar_one_or_none()
        if row:
            return row
        row = ProductRow(
            slug=slug, category=category,
            external_id=ep.product_id, brand=ep.brand, model=ep.model,
        )
        s.add(row)
        s.flush()
        return row

    def _upsert_page(self, s: Session, product: ProductRow, page: PdRawProductPage) -> ProductPageRow:
        row = s.execute(
            select(ProductPageRow).where(
                ProductPageRow.product_id == product.id, ProductPageRow.url == page.url,
            )
        ).scalar_one_or_none()
        if row:
            if page.raw_specs and page.raw_specs != row.raw_specs:
                row.raw_specs = page.raw_specs
            row.title = page.title or row.title
            row.description = page.description or row.description
            return row
        row = ProductPageRow(
            product_id=product.id,
            source=page.source,
            url=page.url,
            title=page.title,
            raw_specs=page.raw_specs or {},
            description=page.description,
        )
        s.add(row)
        s.flush()
        return row

    def _write_snapshot(self, run_id, category, slug, stats, schema_pd, enriched_pd) -> None:
        out_path = Path(settings.enriched_dir) / f"{run_id}.json"
        payload = {
            "run_id": run_id,
            "category": category,
            "slug": slug,
            "stats": stats,
            "schema": json.loads(schema_pd.model_dump_json()) if schema_pd else None,
            "products": [json.loads(p.model_dump_json()) for p in enriched_pd],
        }
        out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def list_runs(self, limit: int = 20) -> list[dict]:
        with Session(Repo._engine) as s:
            rows = s.execute(
                select(Run).order_by(Run.started_at.desc()).limit(limit)
            ).scalars().all()
            return [{
                "id": r.id, "category": r.category, "slug": r.slug,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "stats": r.stats, "schema_id": r.schema_id,
            } for r in rows]

    def get_run(self, run_id: str) -> dict | None:
        with Session(Repo._engine) as s:
            r = s.get(Run, run_id)
            if not r:
                return None
            return {
                "id": r.id, "category": r.category, "slug": r.slug,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "stats": r.stats, "schema_id": r.schema_id,
            }

    def list_products(self, run_id: str) -> list[dict]:
        with Session(Repo._engine) as s:
            rows = s.execute(
                select(EnrichedProductRow)
                .where(EnrichedProductRow.run_id == run_id)
                .options(joinedload(EnrichedProductRow.product))
            ).unique().scalars().all()
            out = []
            for ep in rows:
                p = ep.product
                out.append({
                    "product_id": p.external_id if p else "",
                    "category": p.category if p else "",
                    "brand": p.brand if p else "",
                    "model": p.model if p else "",
                    "seed_source": ep.seed_source,
                    "seed_url": ep.seed_url,
                    "coverage": ep.coverage,
                    "flags": ep.flags_json,
                    "fields": ep.fields_json,
                })
            return out

    def latest_schema(self, category_or_slug: str) -> dict | None:
        with Session(Repo._engine) as s:
            row = s.execute(
                select(SchemaRow)
                .where((SchemaRow.category == category_or_slug) | (SchemaRow.slug == category_or_slug))
                .order_by(SchemaRow.created_at.desc())
            ).scalars().first()
            if not row:
                return None
            return {
                "category": row.category,
                "slug": row.slug,
                "version": row.version,
                "induced_from": row.induced_from,
                "fields": row.fields_json,
            }


def _serialize_fields(ep: PdEnrichedProduct) -> dict:
    out: dict[str, dict] = {}
    for name, ef in ep.fields.items():
        obs_list = []
        for obs in ef.observations:
            eff = settings.trust_weights.get(obs.source_type, 0.5) * obs.intrinsic_confidence
            obs_list.append({
                "value": obs.value,
                "source_type": obs.source_type,
                "source_url": obs.source_url,
                "intrinsic_confidence": obs.intrinsic_confidence,
                "effective_score": round(eff, 4),
            })

        max_score = max((o["effective_score"] for o in obs_list), default=0.0)
        winner_val = _canon(ef.value)
        winner_assigned = False
        for o in obs_list:
            if not winner_assigned and o["effective_score"] == max_score and _canon(o["value"]) == winner_val:
                o["is_winner"] = True
                winner_assigned = True
            else:
                o["is_winner"] = False

        out[name] = {
            "value": ef.value,
            "confidence": ef.confidence,
            "validated": ef.validated,
            "flags": ef.flags,
            "observations": obs_list,
        }
    return out


def _canon(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def _slugify(s: str) -> str:
    from slugify import slugify
    return slugify(s or "unknown")
