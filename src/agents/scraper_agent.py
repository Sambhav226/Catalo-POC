from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from src.config import settings
from src.models import RawProductPage, Product, PipelineState, NodeError
from src.tools import HTTPScraper, FirecrawlScraper

log = logging.getLogger("agent.scraper")


class ScraperAgent:
    def __init__(self, http: HTTPScraper | None = None, firecrawl: FirecrawlScraper | None = None):
        self.http = http or HTTPScraper()
        self.firecrawl = firecrawl or FirecrawlScraper()

    def run(self, state: PipelineState) -> dict:
        errors: list[NodeError] = list(state.get("errors", []))
        limit = int(state.get("limit") or 0)

        seed_pages = self._load_seed(state.get("slug") or _slugify(state.get("category", "")))
        seed_urls = state.get("seed_urls") or []

        live_pages: list[RawProductPage] = []
        for url in seed_urls:
            page = self._fetch_live(url)
            if page:
                live_pages.append(page)
            else:
                errors.append(NodeError(node="scraper", message=f"could not fetch {url}"))

        all_pages = seed_pages + live_pages
        products = _group_into_products(all_pages, state.get("category", ""))

        if limit and limit > 0:
            products = products[:limit]
            keep_ids = {p.product_id for p in products}
            all_pages = [p for p in all_pages if p.product_id in keep_ids]

        log.info("scraper: %d pages across %d products", len(all_pages), len(products))

        return {
            "raw_pages": all_pages,
            "products": products,
            "errors": errors,
        }

    def _load_seed(self, slug: str) -> list[RawProductPage]:
        if not slug:
            return []
        path = Path(settings.seed_dir) / slug / "products.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        pages: list[RawProductPage] = []
        for item in data:
            pages.append(RawProductPage(**item))
        return pages

    def _fetch_live(self, url: str) -> RawProductPage | None:
        page = self.http.fetch(url)
        if not page.ok:
            page = self.firecrawl.fetch(url)
        if not page.ok:
            return None
        raw_specs: dict[str, str] = {}
        for tbl in page.tables:
            raw_specs.update(tbl)
        from src.tools.scraper import domain_of
        source = _source_of(domain_of(url))
        return RawProductPage(
            product_id=_stable_id(url),
            source=source,
            url=url,
            raw_specs=raw_specs,
            title=page.text[:200] if page.text else None,
        )


def _slugify(s: str) -> str:
    from slugify import slugify
    return slugify(s)


def _stable_id(url: str) -> str:
    import hashlib
    return "live-" + hashlib.md5(url.encode()).hexdigest()[:8]


def _source_of(domain: str) -> str:
    if "amazon" in domain:
        return "amazon"
    if "flipkart" in domain:
        return "flipkart"
    if "croma" in domain:
        return "croma"
    if "samsung" in domain:
        return "samsung"
    if "lg.com" in domain:
        return "lg"
    if "sony" in domain:
        return "sony"
    return domain or "unknown"


def _group_into_products(pages: list[RawProductPage], category: str) -> list[Product]:
    grouped: dict[str, list[RawProductPage]] = defaultdict(list)
    for p in pages:
        grouped[p.product_id].append(p)

    out: list[Product] = []
    for pid, page_list in grouped.items():
        seed = next((p for p in page_list if p.source in {"croma", "flipkart"}), page_list[0])
        out.append(Product(
            product_id=pid,
            category=category,
            brand=seed.brand,
            model=seed.model,
            seed_source=seed.source,
            seed_url=seed.url,
            pages=page_list,
        ))
    return out
