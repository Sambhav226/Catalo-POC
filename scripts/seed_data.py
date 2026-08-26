from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.tools import HTTPScraper, FirecrawlScraper  # noqa: E402
from src.tools.scraper import domain_of  # noqa: E402

app = typer.Typer(help="Collect seed data for a category from a list of URLs.")
console = Console()


@app.command()
def main(
    slug: str = typer.Option(..., "--slug", "-s"),
    urls_file: str = typer.Option(..., "--urls", "-u", help="One URL per line."),
    product_id_prefix: str = typer.Option("tv-", "--prefix"),
):
    out_dir = Path(settings.seed_dir) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = [u.strip() for u in Path(urls_file).read_text(encoding="utf-8").splitlines() if u.strip()]

    http = HTTPScraper()
    firecrawl = FirecrawlScraper()

    products: list[dict] = []
    for i, url in enumerate(urls, 1):
        page = http.fetch(url)
        if not page.ok:
            page = firecrawl.fetch(url)
        if not page.ok:
            console.print(f"[red]skip[/] {url}")
            continue
        raw_specs: dict[str, str] = {}
        for tbl in page.tables:
            raw_specs.update(tbl)
        products.append({
            "product_id": f"{product_id_prefix}{i:03d}",
            "source": _source_from_domain(domain_of(url)),
            "url": url,
            "brand": None,
            "model": None,
            "title": (page.text or "")[:200],
            "raw_specs": raw_specs,
            "description": (page.text or "")[:1500],
        })

    out_path = out_dir / "products.json"
    out_path.write_text(json.dumps(products, indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/] {out_path} · {len(products)} products")


def _source_from_domain(d: str) -> str:
    if "amazon" in d:
        return "amazon"
    if "flipkart" in d:
        return "flipkart"
    if "croma" in d:
        return "croma"
    if "samsung" in d:
        return "samsung"
    if "lg.com" in d:
        return "lg"
    if "sony" in d:
        return "sony"
    return d or "unknown"


if __name__ == "__main__":
    app()
