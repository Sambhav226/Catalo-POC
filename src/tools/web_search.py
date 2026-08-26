from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import httpx

from src.config import settings

log = logging.getLogger("web_search")


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    source_domain: str = ""


class WebSearch:
    def __init__(self):
        self._tavily = None
        if settings.tavily_api_key and not settings.is_offline():
            try:
                from tavily import TavilyClient
                self._tavily = TavilyClient(api_key=settings.tavily_api_key)
            except Exception as e:
                log.warning("Tavily init failed, falling back to DuckDuckGo: %s", e)

    def search(self, query: str, prefer_domains: list[str] | None = None, top_k: int = 5) -> list[SearchHit]:
        prefer_domains = [d.lower() for d in (prefer_domains or [])]

        if settings.is_offline():
            return []

        hits: list[SearchHit] = []
        try:
            if self._tavily:
                r = self._tavily.search(query=query, max_results=top_k * 2)
                for item in r.get("results", []):
                    hits.append(SearchHit(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        score=float(item.get("score", 0.0)),
                        source_domain=_domain_of(item.get("url", "")),
                    ))
            else:
                hits = _duckduckgo_html(query, top_k * 2)
        except Exception as e:
            log.warning("Search failed for %r: %s", query, e)
            return []

        for h in hits:
            h.score += sum(0.5 for d in prefer_domains if d in h.source_domain)

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _duckduckgo_html(query: str, k: int) -> list[SearchHit]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    r = httpx.get(url, timeout=10.0, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    })
    r.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[SearchHit] = []
    for a in soup.select("a.result__a")[:k]:
        href = a.get("href", "")
        title = a.get_text(strip=True)
        snippet_el = a.find_parent().find_next_sibling("a") if a.find_parent() else None
        out.append(SearchHit(title=title, url=href, snippet="", score=1.0, source_domain=_domain_of(href)))
    return out
