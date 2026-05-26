# Dossigraphica — Atlas of Corporate Intelligence

<p align="center">
  <img src="public/readme-animation.svg" alt="Dossigraphica — GEOINT Cartographic Dashboard Animation" width="100%">
</p>

**[Dossigraphica](https://zhicheng-wang.com/Dossigraphica/)** is an autonomous geographic intelligence platform. Given a company name, it researches the open web, extracts structured intelligence, and visualises corporate footprints, supply chain dependencies, and geopolitical risk profiles on an interactive 3D globe.

The core artifact is an **8-stage async research pipeline** written in Python — a deterministic orchestration engine that plans searches, extracts content via map-reduce LLM sieving, detects geographic data gaps, fills them with targeted enrichment, and drafts structured JSON and Markdown dossiers in parallel. All streamed to the frontend via SSE.

## Key Features

- **Autonomous Research Pipeline** — An 8-stage deterministic workflow that starts from a company name and ends with structured geographic intelligence. No manual intervention.
- **Provider-Agnostic LLM Engine** — LiteLLM routes all model calls through a unified interface. Currently runs on Gemini (flash-lite-preview, 10 parallel, 32K context), but can switch to DeepSeek, Featherless, or a local llama.cpp instance with a single environment variable.
- **Interactive 3D Globe** — Parchment-and-ink styled globe built with react-globe.gl and Three.js. Clickable intelligence nodes, animated supply chain arcs, hover-based adjacency highlighting, and stacked node positioning for overlapping coordinates.
- **Map-Reduce Fact Extraction** — Fetched content is token-chunked, each chunk is LLM-extracted into categorised facts (OFFICES, REVENUE, SUPPLY_CHAIN, RISKS, CUSTOMERS, CORPORATE), and results are deduplicated into a unified fact pool.
- **Programmatic Gap Detection** — The entity assembly step runs the same extraction the drafter uses, then *programmatically* inspects the output for missing geographic data. Missing addresses, coordinates, or cities trigger targeted enrichment searches — no LLM decides what's missing.
- **Parallel Drafting** — 13 concurrent LLM calls produce the final output: 7 JSON schemas and 6 Markdown narrative sections, all generated simultaneously and assembled into a complete dossier.
- **Global Strategy Hub** — Cross-company analysis panels: Value Chain Matrix (buyer-supplier dependencies), Macro Risk Convergence (aggregated regional risks), and Chokepoint Analysis (critical infrastructure bottlenecks).
- **Inference Tracing** — Every LLM call is logged to disk with its input prompt, output JSON, and reasoning field, indexed sequentially for post-mortem replay.

## Tech Stack

### Frontend
- **Framework:** React 19, TypeScript, Vite 7
- **Styling:** Tailwind CSS 4
- **State:** Zustand 5
- **Visualization:** react-globe.gl, Three.js, Lucide React
- **Content:** React Markdown, Rehype Raw, Remark GFM

### Research Backend (Python Sidecar)
- **API:** FastAPI with SSE streaming
- **Orchestration:** Async generators with multiplexed task scheduling
- **LLM Client:** LiteLLM (provider-agnostic: Gemini, DeepSeek, llama.cpp, Featherless)
- **Extraction:** Pydantic strict schemas, json-repair for robustness
- **Search:** Brave Discovery API / TinyFish Search API
- **Fetch:** Jina Reader API / TinyFish Fetch API (with cross-provider fallback)
- **Caching:** Disk-based caches for search results, fetched content, geocoder lookups

## Project Structure

```text
├── public/
│   ├── data/
│   │   ├── intel/           # Per-company JSON intelligence files
│   │   ├── research/        # Per-company Markdown reports + global analysis
│   │   └── countries.json   # GeoJSON for globe polygons
│   └── logo.svg             # Project favicon
├── python-sidecar/
│   ├── main.py              # FastAPI entry point
│   ├── pipeline.py          # 8-stage orchestration engine
│   ├── llm.py               # LLM client (structured gen, map-reduce, streaming)
│   ├── provider.py          # Provider config (Gemini, DeepSeek, local)
│   ├── schemas.py           # All Pydantic models for the pipeline
│   └── tasks/
│       ├── planner.py       # Programmatic query generation (no LLM)
│       ├── search.py        # Brave / TinyFish search dispatch
│       ├── source_triage.py # LLM-based spam filter
│       ├── extractor.py     # Jina / TinyFish fetch with rate limiting
│       ├── preprocessor.py  # Token-chunking + fact extraction (map-reduce)
│       ├── entity_assembly.py  # Gap detection → enrichment queries
│       └── drafter.py       # Parallel JSON + Markdown generation
├── src/
│   ├── components/
│   │   ├── Globe.tsx        # 3D globe with nodes, arcs, layers
│   │   ├── Header.tsx       # Masthead with company selector
│   │   ├── IntelPanel.tsx   # Per-company dossier panel
│   │   ├── GlobalPanel.tsx  # Cross-company strategy hub
│   │   └── EntityPopup.tsx  # Click-to-inspect popup
│   ├── useGeoIntel.ts       # Zustand store + SSE connection
│   └── types.ts             # TypeScript schema mirroring Pydantic models
├── scripts/
│   ├── register_intel.py    # Syncs intel files to companies.json
│   └── generate_analysis.py # Aggregates cross-company analysis
└── docker-compose.yaml      # Optional: local llama.cpp server
```

## Getting Started

### Prerequisites
- **Node.js** v20+
- **Python** 3.10+
- **API keys** in `.env`: `BRAVE_SEARCH_API_KEY`, `GEMINI_API_KEY` (or configure DeepSeek/local)

### Installation

```bash
# Frontend
npm install

# Python sidecar
cd python-sidecar
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### Running

```bash
# Terminal 1: Python research backend
cd python-sidecar
source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2: Vite frontend
npm run dev
```

The pipeline defaults to Gemini. To use a local model, set `LLM_PROVIDER=local` in `.env`, start `docker-compose up -d`, and the sidecar will route calls to `http://localhost:8081`.

## Data Management

- **Register a new company:** Drop its JSON intel file in `public/data/intel/`, then run `python scripts/register_intel.py` to rebuild `src/data/companies.json`.
- **Regenerate global analysis:** Run `python scripts/generate_analysis.py` to rebuild the Value Chain Matrix, Risk Convergence, and Chokepoint Analysis from all registered intel files.
- **Live research:** Use the "View Dossier" button in the header to trigger the pipeline against any registered company.

## License

© 2026 Dossigraphica Project. Built for strategic analysis and geographic visualisation.
Data sources: Brave Search, Jina Reader, SEC filings, public reports.
