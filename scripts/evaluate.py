from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage import Repo  # noqa: E402

app = typer.Typer()
console = Console()


@app.command()
def main(
    run_id: str = typer.Option(..., "--run-id", "-r"),
):
    repo = Repo()
    run = repo.get_run(run_id)
    if not run:
        console.print(f"[red]unknown run:[/] {run_id}")
        raise typer.Exit(2)

    products = repo.list_products(run_id)
    if not products:
        console.print(f"[red]no products for run:[/] {run_id}")
        raise typer.Exit(3)

    schema = repo.latest_schema(run["category"])
    schema_field_count = len(schema.get("fields", [])) if schema else 0

    filled_fields = 0
    provenance_depths: list[float] = []
    conflicts = 0
    conflict_eligible = 0

    for p in products:
        for field, ef in p["fields"].items():
            if ef.get("value") not in (None, ""):
                filled_fields += 1
            obs = ef.get("observations", [])
            if obs:
                provenance_depths.append(len(obs))
            if len(obs) >= 2:
                conflict_eligible += 1
                values = {str(o.get("value")).strip().lower() for o in obs}
                if len(values) >= 2:
                    conflicts += 1

    total_schema_slots = max(1, schema_field_count) * len(products)
    coverage = filled_fields / total_schema_slots
    avg_depth = statistics.mean(provenance_depths) if provenance_depths else 0.0
    conflict_rate = conflicts / max(1, conflict_eligible)

    t = Table(title=f"Evaluation · {run_id}")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Products", str(len(products)))
    t.add_row("Category", run["category"])
    t.add_row("Schema fields", str(schema_field_count))
    t.add_row("Filled slots", f"{filled_fields} / {total_schema_slots}")
    t.add_row("Coverage (schema)", f"{coverage:.1%}")
    t.add_row("Avg provenance depth", f"{avg_depth:.2f}")
    t.add_row("Conflict rate", f"{conflict_rate:.1%}")
    console.print(t)


if __name__ == "__main__":
    app()
