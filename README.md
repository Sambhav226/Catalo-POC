# Catalog Enrichment POC

Agentic pipeline that takes a leaf category from one e-commerce site (e.g. 4K LED TVs from Croma), induces a canonical schema from multiple sources (Amazon, Samsung, LG, Sony), and produces enriched product records where every field is filled from the most trustworthy source.

## Quickstart

```bash
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
```

## Documentation

| Doc | What's inside |
| --- | --- |
| [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) | End-to-end trace: every entry point → every node → every DB row. Read this first if you want to understand the system in one pass. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The chosen design (LangGraph multi-agent), data flow, state contract, why it wins. |
| [docs/ALTERNATIVES.md](docs/ALTERNATIVES.md) | Two rejected designs (Monolithic LLM + RAG, CrewAI/AutoGen autonomous swarm) — with pros, cons, and the honest reasons they lost. |
| [docs/COMPONENTS.md](docs/COMPONENTS.md) | Deep dive on every module: agents, tools, graph, storage, API, UI. |
| [docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) | Normalised DB schema — ERD, per-table specs, query patterns, migration plan. |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local, Docker, and cloud (ECS / Cloud Run / K8s) deployment paths. |
| [docs/DATA_STRATEGY.md](docs/DATA_STRATEGY.md) | How the seed data was collected, legal/ToS notes, and how to plug in Firecrawl / Bright Data / SerpAPI for real scale. |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Coverage, conflict-rate, and hallucination metrics used to score the enrichment. |

## Project layout

```
catalog-enrichment-poc/
├── data/
│   ├── seed/            # Real, checked-in product data from Croma/Amazon/Samsung/LG/Sony
│   └── enriched/        # Pipeline output (git-ignored at scale)
├── docs/                # Design & ops docs
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
