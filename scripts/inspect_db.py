from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "enriched" / "catalog.db"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not DB.exists():
    print(f"no db at {DB}")
    raise SystemExit(1)

c = sqlite3.connect(str(DB))

print("=" * 78)
print(f"DB   : {DB}")
print(f"Size : {DB.stat().st_size:,} bytes")
print("=" * 78)

print("\n[ TABLES ]")
for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    n = c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"  {name:22s} {n:>6} rows")


def dump(title: str, sql: str, headers: list[str]) -> None:
    print(f"\n[ {title} ]")
    rows = c.execute(sql).fetchall()
    if not rows:
        print("  (empty)")
        return
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


dump("runs (latest 5)",
     "SELECT id, category, status, started_at FROM runs ORDER BY started_at DESC LIMIT 5",
     ["id", "category", "status", "started_at"])

dump("schemas (latest 3)",
     "SELECT id, slug, version, is_active, created_at FROM schemas ORDER BY created_at DESC LIMIT 3",
     ["id", "slug", "version", "is_active", "created_at"])

dump("products",
     "SELECT id, external_id, brand, model FROM products ORDER BY id",
     ["id", "external_id", "brand", "model"])

dump("product_pages (per product count)",
     """SELECT p.external_id, COUNT(pp.id) AS pages
        FROM products p LEFT JOIN product_pages pp ON pp.product_id = p.id
        GROUP BY p.id ORDER BY p.id""",
     ["external_id", "pages"])

dump("enriched_products (latest run)",
     """SELECT p.external_id, ep.coverage, ep.seed_source, ep.run_id
        FROM enriched_products ep
        JOIN products p ON p.id = ep.product_id
        WHERE ep.run_id = (SELECT id FROM runs ORDER BY started_at DESC LIMIT 1)
        ORDER BY p.external_id""",
     ["external_id", "coverage", "seed_source", "run_id"])


print("\n[ audit trail from JSON — tv-001 / screen_size_inches ]")
row = c.execute(
    """SELECT ep.fields_json FROM enriched_products ep
       JOIN products p ON p.id = ep.product_id
       WHERE p.external_id = 'tv-001'
       ORDER BY ep.id DESC LIMIT 1"""
).fetchone()
if row:
    fields = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    f = fields.get("screen_size_inches")
    if f:
        print(f"  final value : {f['value']}   confidence: {f['confidence']}   validated: {f['validated']}")
        print(f"  observations:")
        for o in f.get("observations", []):
            mark = "*" if o.get("is_winner") else " "
            print(f"   {mark} {o['source_type']:<13} score={o['effective_score']:<6}  value={o['value']}")
