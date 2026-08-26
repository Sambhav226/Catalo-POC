from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.tools.cache import Cache

log = logging.getLogger("scraper")


@dataclass
class ScrapedPage:
    url: str
    status: int
    text: str = ""
    tables: list[dict] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    ok: bool = False


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class HTTPScraper:
    def __init__(self, cache: Cache | None = None, timeout: float = 15.0):
        self.cache = cache or Cache(settings.cache_dir)
        self.timeout = timeout

    def fetch(self, url: str) -> ScrapedPage:
        cached = self.cache.get_url(url)
        if cached is not None:
            return _parse(url, 200, cached)

        try:
            r = httpx.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True)
        except Exception as e:
            log.warning("HTTPScraper failed on %s: %s", url, e)
            return ScrapedPage(url=url, status=0, ok=False)

        if r.status_code == 200 and len(r.text) > 500:
            self.cache.set_url(url, r.text)
            return _parse(url, r.status_code, r.text)

        return ScrapedPage(url=url, status=r.status_code, ok=False)


class FirecrawlScraper:
    def __init__(self):
        self.enabled = bool(settings.firecrawl_api_key) and not settings.is_offline()
        self._client = None
        if self.enabled:
            try:
                from firecrawl import FirecrawlApp
                self._client = FirecrawlApp(api_key=settings.firecrawl_api_key)
            except Exception as e:
                log.warning("Firecrawl init failed: %s", e)
                self.enabled = False

    def fetch(self, url: str) -> ScrapedPage:
        if not self.enabled or not self._client:
            return ScrapedPage(url=url, status=0, ok=False)
        try:
            r = self._client.scrape_url(url, params={"formats": ["markdown", "html"]})
            html = r.get("html") or r.get("markdown") or ""
            return _parse(url, 200, html)
        except Exception as e:
            log.warning("Firecrawl failed on %s: %s", url, e)
            return ScrapedPage(url=url, status=0, ok=False)


def _parse(url: str, status: int, html: str) -> ScrapedPage:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    tables = _extract_tables(soup)
    links = [a.get("href", "") for a in soup.find_all("a") if a.get("href")]
    return ScrapedPage(url=url, status=status, text=text, tables=tables, links=links, ok=True)


def _extract_tables(soup: BeautifulSoup) -> list[dict]:
    out: list[dict] = []
    for table in soup.find_all("table"):
        row_map: dict[str, str] = {}
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                k = cells[0].get_text(" ", strip=True)
                v = cells[1].get_text(" ", strip=True)
                if k and v:
                    row_map[k] = v
        if row_map:
            out.append(row_map)
    for dl in soup.find_all("dl"):
        pairs: dict[str, str] = {}
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            k = dt.get_text(" ", strip=True)
            v = dd.get_text(" ", strip=True)
            if k and v:
                pairs[k] = v
        if pairs:
            out.append(pairs)
    return out


def domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
