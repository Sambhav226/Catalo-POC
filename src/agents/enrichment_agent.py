from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pydantic import BaseModel

from src.config import settings
from src.models import (
    CategorySchema, Product, RawProductPage, FieldObservation,
    EnrichedProduct, EnrichedField, PipelineState,
)
from src.tools import LLMClient, WebSearch, HTTPScraper, FirecrawlScraper

log = logging.getLogger("agent.enrichment")


class SpecExtraction(BaseModel):
    fields: dict[str, Any]


class EnrichmentExtraction(BaseModel):
    fields: dict[str, Any]


EXTRACT_SYSTEM = (
    "You extract structured product attributes from raw HTML/text. Return only fields you can "
    "justify from the given content. Coerce values to the requested dtype. Never invent data."
)


class EnrichmentAgent:
    def __init__(
        self,
        llm: LLMClient | None = None,
        search: WebSearch | None = None,
        http: HTTPScraper | None = None,
        firecrawl: FirecrawlScraper | None = None,
    ):
        self.llm = llm or LLMClient()
        self.search = search or WebSearch()
        self.http = http or HTTPScraper()
        self.firecrawl = firecrawl or FirecrawlScraper()

    def run(self, state: PipelineState) -> dict:
        products: list[Product] = state.get("products", [])
        schema: CategorySchema = state.get("category_schema")
        if not schema:
            return {"enriched": []}

        concurrency = max(1, int(settings.enrichment_concurrency))
        results: list[EnrichedProduct] = [None] * len(products)  # type: ignore

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(self._enrich_one, p, schema): idx
                for idx, p in enumerate(products)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    results[idx] = fut.result()
                except Exception as e:
                    p = products[idx]
                    log.warning("enrichment failed for %s: %s", p.product_id, e)
                    results[idx] = _empty_enriched(p, schema)

        return {"enriched": [r for r in results if r is not None]}

    def _enrich_one(self, product: Product, schema: CategorySchema) -> EnrichedProduct:
        observations: dict[str, list[FieldObservation]] = {}

        for page in product.pages:
            extracted = self._extract_from_page(page, schema)
            for field, value in extracted.items():
                observations.setdefault(field, []).append(FieldObservation(
                    field=field,
                    value=value,
                    source_url=page.url,
                    source_type=settings.source_type(page.url or page.source),
                    intrinsic_confidence=0.9,
                ))

        wanted = set(schema.field_names())
        for round_idx in range(settings.max_enrichment_rounds):
            missing = [f for f in wanted if f not in observations]
            if not missing:
                break
            new_pages = self._search_and_scrape(product, missing)
            if not new_pages:
                break
            for page in new_pages:
                extracted = self._extract_from_page(page, schema, focus_fields=missing)
                for field, value in extracted.items():
                    observations.setdefault(field, []).append(FieldObservation(
                        field=field,
                        value=value,
                        source_url=page.url,
                        source_type=settings.source_type(page.url or page.source),
                        intrinsic_confidence=0.75,
                    ))
                product.pages.append(page)

        enriched_fields: dict[str, EnrichedField] = {}
        for field, obs_list in observations.items():
            enriched_fields[field] = EnrichedField(
                value=obs_list[0].value,
                confidence=0.0,
                provenance=[o.source_url for o in obs_list],
                observations=obs_list,
            )

        return EnrichedProduct(
            product_id=product.product_id,
            category=product.category,
            brand=product.brand,
            model=product.model,
            fields=enriched_fields,
            seed_source=product.seed_source,
            seed_url=product.seed_url,
        )

    def _extract_from_page(
        self,
        page: RawProductPage,
        schema: CategorySchema,
        focus_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        fields = focus_fields or schema.field_names()
        raw_specs_json = json.dumps(page.raw_specs or {})
        prompt = (
            f"CATEGORY = {page.title or ''}\n"
            f"SOURCE = {page.source}\n"
            f"URL = {page.url}\n"
            f"WANTED_FIELDS = {json.dumps(fields)}\n"
            f"RAW_SPECS_JSON = {raw_specs_json}\n"
            f"PAGE_TEXT = \"\"\"{(page.description or '')[:2000]}\"\"\"\n\n"
            "Extract as many WANTED_FIELDS as you can from RAW_SPECS_JSON and PAGE_TEXT. "
            "Return {\"fields\": {name: value}}. Omit fields you can't justify."
        )
        try:
            result = self.llm.structured_call(
                system=EXTRACT_SYSTEM, user=prompt, response_model=SpecExtraction,
            )
            return result.fields or {}
        except Exception as e:
            log.debug("extraction failed: %s", e)
            return {}

    def _search_and_scrape(self, product: Product, missing: list[str]) -> list[RawProductPage]:
        if not product.brand or not product.model:
            return []
        prefer = _manufacturer_domain(product.brand)
        query = f"{product.brand} {product.model} specifications"
        hits = self.search.search(query, prefer_domains=[prefer, "amazon.in", "flipkart.com"], top_k=3)
        already = {p.url for p in product.pages}
        new_pages: list[RawProductPage] = []
        for h in hits:
            if h.url in already:
                continue
            page = self.http.fetch(h.url)
            if not page.ok:
                page = self.firecrawl.fetch(h.url)
            if not page.ok:
                continue
            raw_specs: dict[str, str] = {}
            for tbl in page.tables:
                raw_specs.update(tbl)
            new_pages.append(RawProductPage(
                product_id=product.product_id,
                source=h.source_domain,
                url=h.url,
                brand=product.brand,
                model=product.model,
                title=h.title,
                description=page.text[:3000],
                raw_specs=raw_specs,
            ))
        return new_pages


def _manufacturer_domain(brand: str) -> str:
    b = (brand or "").lower()
    mapping = {
        "samsung": "samsung.com",
        "lg": "lg.com",
        "sony": "sony.co.in",
        "tcl": "tcl.com",
        "xiaomi": "mi.com",
        "mi": "mi.com",
        "hisense": "hisense.co.in",
        "vu": "vutvs.com",
    }
    return mapping.get(b, f"{b}.com")


def _empty_enriched(product: Product, schema: CategorySchema) -> EnrichedProduct:
    return EnrichedProduct(
        product_id=product.product_id,
        category=product.category,
        brand=product.brand,
        model=product.model,
        seed_source=product.seed_source,
        seed_url=product.seed_url,
        flags=["enrichment_failed"],
    )
