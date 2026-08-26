from __future__ import annotations

from typing import TypedDict

from .schema import CategorySchema
from .product import RawProductPage, Product, EnrichedProduct, NodeError


class PipelineState(TypedDict, total=False):
    run_id: str
    category: str
    slug: str
    seed_source: str
    seed_urls: list[str]
    limit: int

    raw_pages: list[RawProductPage]
    category_schema: CategorySchema
    products: list[Product]
    enriched: list[EnrichedProduct]

    errors: list[NodeError]
    stats: dict
