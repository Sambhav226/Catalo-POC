from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class RawProductPage(BaseModel):
    product_id: str
    source: str
    url: str
    brand: str | None = None
    model: str | None = None
    title: str | None = None
    raw_specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    images: list[str] = Field(default_factory=list)


class Product(BaseModel):
    product_id: str
    category: str
    brand: str | None = None
    model: str | None = None
    seed_source: str | None = None
    seed_url: str | None = None
    pages: list[RawProductPage] = Field(default_factory=list)


class FieldObservation(BaseModel):
    field: str
    value: Any
    source_url: str
    source_type: str
    intrinsic_confidence: float = 0.8
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class EnrichedField(BaseModel):
    value: Any
    confidence: float
    provenance: list[str] = Field(default_factory=list)
    observations: list[FieldObservation] = Field(default_factory=list)
    validated: bool = False
    flags: list[str] = Field(default_factory=list)


class EnrichedProduct(BaseModel):
    product_id: str
    category: str
    brand: str | None = None
    model: str | None = None
    fields: dict[str, EnrichedField] = Field(default_factory=dict)
    coverage: float = 0.0
    flags: list[str] = Field(default_factory=list)
    seed_source: str | None = None
    seed_url: str | None = None


class NodeError(BaseModel):
    node: str
    message: str
    at: datetime = Field(default_factory=datetime.utcnow)
