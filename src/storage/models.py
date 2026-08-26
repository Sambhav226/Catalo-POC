from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, JSON, Text,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str] = mapped_column(String, index=True)
    slug: Mapped[str] = mapped_column(String, index=True)
    schema_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("schemas.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    seed_source: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    schema: Mapped["SchemaRow | None"] = relationship(back_populates="runs")
    enriched: Mapped[list["EnrichedProductRow"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SchemaRow(Base):
    __tablename__ = "schemas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String, default="1.0.0")
    fields_json: Mapped[list] = mapped_column(JSON, default=list)
    induced_from: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    runs: Mapped[list[Run]] = relationship(back_populates="schema")


class ProductRow(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, index=True)
    slug: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    brand: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pages: Mapped[list["ProductPageRow"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    enrichments: Mapped[list["EnrichedProductRow"]] = relationship(back_populates="product")

    __table_args__ = (
        UniqueConstraint("slug", "external_id", name="uq_product_slug_external"),
        Index("ix_products_brand_model", "brand", "model"),
    )


class ProductPageRow(Base):
    __tablename__ = "product_pages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), index=True)
    source: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_specs: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped[ProductRow] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("product_id", "url", name="uq_page_product_url"),
    )


class EnrichedProductRow(Base):
    __tablename__ = "enriched_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), index=True)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    seed_source: Mapped[str | None] = mapped_column(String, nullable=True)
    seed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    flags_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped[Run] = relationship(back_populates="enriched")
    product: Mapped[ProductRow] = relationship(back_populates="enrichments")

    __table_args__ = (
        UniqueConstraint("run_id", "product_id", name="uq_enriched_run_product"),
    )
