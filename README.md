# Catalog Enrichment POC

Agentic pipeline that takes a leaf category from one e-commerce site (e.g. 4K LED TVs from Croma), induces a canonical schema from multiple sources (Amazon, Samsung, LG, Sony), and produces enriched product records where every field is filled from the most trustworthy source.

## Quickstart

git clone <repo> catalog-enrichment-poc
cd catalog-enrichment-poc

cp .env.example .env
# fill in OPENAI_API_KEY and (optionally) TAVILY_API_KEY / FIRECRAWL_API_KEY

pip install -r requirements.txt

# One-shot enrichment on the bundled 4K LED TV seed set:
python -m scripts.run_enrichment --category "4K LED TV" --limit 5

# Or spin up the full stack:
docker compose -f docker/docker-compose.yml up --build
# API:  http://localhost:8000/docs
# UI :  http://localhost:8501

## Documentation


| ARCHITECTURE.md](ARCHITECTURE.md) | The chosen design (LangGraph multi-agent), data flow, state contract.
## Project layout

```
catalog-enrichment-poc/
├── data/
│   ├── seed/            # Real, checked-in product data from Croma/Amazon/Samsung/LG/Sony
│   └── enriched/        # Pipeline output (git-ignored at scale)
├── docker/              # Dockerfile + docker-compose
├── scripts/             # CLI runners (seed, enrich, eval)
├── src/
│   ├── agents/          # 5 role-specific agents
│   ├── graph/           # LangGraph workflow & state
│   ├── tools/           # Scraper, web search, LLM client
│   ├── models/          # Pydantic schemas (Product, CategorySchema, EnrichedProduct)
│   ├── storage/         # SQLite/Postgres persistence
│   └── api/             # FastAPI service
├── ui/                  # Streamlit demo UI
└── tests/               # pytest suite
```
