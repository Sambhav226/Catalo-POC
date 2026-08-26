from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.graph import run_pipeline  # noqa: E402
from src.storage import Repo  # noqa: E402


st.set_page_config(page_title="Catalog Enrichment POC", layout="wide")
st.title("Catalog Enrichment POC")
st.caption("Agentic pipeline · Scraper → Schema → Enrichment → Reconciliation → Validator")

repo = Repo()

with st.sidebar:
    st.header("Run configuration")
    categories = _list_categories()
    slug = st.selectbox("Category (leaf)", options=categories or ["4k-led-tv"], index=0)
    display_name = st.text_input("Display name", value=_pretty(slug))
    seed_source = st.selectbox("Seed source", options=["croma", "flipkart", "amazon"], index=0)
    limit = st.number_input("Limit products", min_value=0, max_value=100, value=5, step=1,
                            help="0 = all products in seed set")

    st.divider()
    st.caption(f"Mode: {'OFFLINE (no API key)' if settings.is_offline() else 'ONLINE (LLM enabled)'}")
    st.caption(f"Model: {settings.openai_model}")
    st.caption(f"DB: {settings.database_url}")

    trigger = st.button("Run enrichment", type="primary")


def _list_categories() -> list[str]:
    seed = Path(settings.seed_dir)
    if not seed.exists():
        return []
    return sorted([p.name for p in seed.iterdir() if p.is_dir() and p.name != "schemas"])


def _pretty(slug: str) -> str:
    return " ".join(w.upper() if w.isdigit() or w.lower() == "led" or w.lower() == "tv" else w.capitalize()
                    for w in slug.replace("-", " ").split())


if trigger:
    with st.spinner("Running the pipeline..."):
        t0 = time.time()
        state = run_pipeline(
            category=display_name,
            slug=slug,
            seed_source=seed_source,
            limit=int(limit),
        )
        elapsed = round(time.time() - t0, 2)

    st.success(f"Run {state['run_id']} completed in {elapsed}s")
    st.session_state["last_run"] = state["run_id"]


run_id = st.session_state.get("last_run")
if not run_id:
    st.info("Configure a run in the sidebar and click **Run enrichment**.")
    st.stop()


col_left, col_right = st.columns([2, 1])

with col_right:
    st.subheader("Recent runs")
    runs = repo.list_runs(limit=10)
    if runs:
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)

    st.subheader("Induced schema")
    schema = repo.latest_schema(_pretty(slug))
    if schema:
        st.caption(f"{len(schema.get('fields', []))} fields · v{schema.get('version', '?')}")
        st.dataframe(
            pd.DataFrame(schema["fields"])[
                [c for c in ["name", "dtype", "unit", "required", "enum_values"] if c in pd.DataFrame(schema["fields"]).columns]
            ],
            use_container_width=True, hide_index=True, height=400,
        )

with col_left:
    st.subheader("Enriched products")
    products = repo.list_products(run_id)
    if not products:
        st.warning("No products for this run.")
        st.stop()

    for prod in products:
        header = f"**{prod['brand']} {prod['model']}** · coverage `{prod['coverage']:.0%}` · seed `{prod['seed_source']}`"
        with st.expander(header, expanded=False):
            rows = []
            for field, ef in prod["fields"].items():
                rows.append({
                    "field": field,
                    "value": ef.get("value"),
                    "confidence": ef.get("confidence"),
                    "validated": ef.get("validated"),
                    "sources": len(ef.get("provenance", [])),
                    "flags": ", ".join(ef.get("flags", [])),
                })
            df = pd.DataFrame(rows).sort_values(by=["validated", "confidence"], ascending=[False, False])
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.caption("Provenance detail")
            prov_rows = []
            for field, ef in prod["fields"].items():
                for obs in ef.get("observations", []):
                    prov_rows.append({
                        "field": field,
                        "value": obs.get("value"),
                        "source_type": obs.get("source_type"),
                        "source_url": obs.get("source_url"),
                    })
            if prov_rows:
                st.dataframe(pd.DataFrame(prov_rows), use_container_width=True, hide_index=True)
