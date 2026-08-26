from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph import run_pipeline  # noqa: E402
from src.config import settings  # noqa: E402

app = typer.Typer(help="Run the catalog enrichment pipeline.")
console = Console()


@app.command()
def main(
    category: str = typer.Option("4K LED TV", "--category", "-c"),
    slug: str = typer.Option("4k-led-tv", "--slug", "-s"),
    seed_source: str = typer.Option("croma", "--seed-source"),
    limit: int = typer.Option(0, "--limit", "-n"),
    out: str = typer.Option("", "--out", "-o", help="Optional file to dump enriched JSON."),
):
    console.rule(f"[bold cyan]Enrichment run · {category} · seed={seed_source} · limit={limit or 'all'}")
    console.print(f"[dim]Offline mode:[/] {settings.is_offline()}   [dim]Model:[/] {settings.openai_model}")

    state = run_pipeline(
        category=category, slug=slug, seed_source=seed_source, limit=limit,
    )

    schema = state.get("category_schema")
    enriched = state.get("enriched", [])
    stats = state.get("stats", {})

    console.rule("[bold]Schema")
    if schema:
        t = Table(show_lines=False)
        for col in ["name", "dtype", "unit", "required"]:
            t.add_column(col)
        for f in schema.fields[:25]:
            t.add_row(f.name, f.dtype, f.unit or "", "yes" if f.required else "")
        console.print(t)
        console.print(f"[dim]... total fields: {len(schema.fields)}[/]")

    console.rule("[bold]Products")
    t = Table()
    t.add_column("id"); t.add_column("brand"); t.add_column("model")
    t.add_column("coverage"); t.add_column("flags")
    for p in enriched:
        t.add_row(p.product_id, p.brand or "", p.model or "",
                  f"{p.coverage:.0%}", ", ".join(p.flags) or "-")
    console.print(t)

    console.rule("[bold]Stats")
    console.print(json.dumps(stats, indent=2))

    if out:
        payload = {
            "run_id": state.get("run_id"),
            "category": state.get("category"),
            "schema": json.loads(schema.model_dump_json()) if schema else None,
            "products": [json.loads(p.model_dump_json()) for p in enriched],
        }
        Path(out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Wrote[/] {out}")


if __name__ == "__main__":
    app()
