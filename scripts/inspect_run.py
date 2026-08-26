from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    files = sorted(glob.glob(str(ROOT / "data" / "enriched" / "run-*.json")))
    if not files:
        print("no runs found")
        return
    latest = files[-1]
    print(f"reading {latest}")
    doc = json.loads(Path(latest).read_text(encoding="utf-8"))
    print(f"run_id: {doc['run_id']}  category: {doc['category']}  products: {len(doc['products'])}")
    print(f"schema fields: {len(doc['schema']['fields'])}")
    for p in doc["products"]:
        print("=" * 100)
        print(f"{p['brand']} {p['model']}  |  coverage={p['coverage']:.0%}  |  seed={p['seed_source']}")
        print(f"URL: {p['seed_url']}")
        for k, v in p["fields"].items():
            val = v["value"]
            conf = v["confidence"]
            n = len(v["provenance"])
            valid = "OK " if v["validated"] else "!! "
            flags = f" flags={v['flags']}" if v["flags"] else ""
            print(f"  {valid}{k:28s}  {str(val)[:45]:45s}  conf={conf:.2f}  n={n}{flags}")


if __name__ == "__main__":
    main()
