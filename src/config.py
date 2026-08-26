from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str = Field(default="")

    tavily_api_key: str = Field(default="")
    firecrawl_api_key: str = Field(default="")

    database_url: str = Field(default=f"sqlite:///{ROOT / 'data' / 'enriched' / 'catalog.db'}")
    cache_dir: str = Field(default=str(ROOT / "data" / ".cache"))

    max_enrichment_rounds: int = Field(default=3)
    enrichment_concurrency: int = Field(default=4)
    log_level: str = Field(default="INFO")

    offline_mode: bool = Field(default=False)

    seed_dir: str = Field(default=str(ROOT / "data" / "seed"))
    enriched_dir: str = Field(default=str(ROOT / "data" / "enriched"))

    trust_weights: dict = Field(default_factory=lambda: {
        "manufacturer": 1.00,
        "marketplace": 0.85,
        "retailer": 0.75,
        "aggregator": 0.55,
        "llm_inferred": 0.30,
    })

    source_type_map: dict = Field(default_factory=lambda: {
        "samsung.com": "manufacturer",
        "lg.com": "manufacturer",
        "sony.co.in": "manufacturer",
        "sony.com": "manufacturer",
        "tcl.com": "manufacturer",
        "mi.com": "manufacturer",
        "xiaomi.com": "manufacturer",
        "amazon.in": "marketplace",
        "amazon.com": "marketplace",
        "flipkart.com": "marketplace",
        "croma.com": "retailer",
        "reliancedigital.in": "retailer",
        "vijaysales.com": "retailer",
    })

    def is_offline(self) -> bool:
        return self.offline_mode or not self.openai_api_key

    def source_type(self, url_or_source: str) -> str:
        s = (url_or_source or "").lower()
        for domain, kind in self.source_type_map.items():
            if domain in s:
                return kind
        known_sources = {
            "croma": "retailer", "flipkart": "marketplace", "amazon": "marketplace",
            "samsung": "manufacturer", "lg": "manufacturer", "sony": "manufacturer",
            "tcl": "manufacturer", "xiaomi": "manufacturer", "mi": "manufacturer",
        }
        return known_sources.get(s, "aggregator")

    def trust_for(self, url_or_source: str) -> float:
        return self.trust_weights.get(self.source_type(url_or_source), 0.5)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    Path(s.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(s.enriched_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    return s


settings = get_settings()
