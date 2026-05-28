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

- **Live research:** Use the "View Dossier" button in the header to trigger the 8-stage pipeline against any registered company.
- **Register intel files:** After the pipeline produces a dossier, run the intel registry to make it visible on the globe.
- **Regenerate global analysis:** After registering new intel, run the analysis generator to rebuild cross-company views.

### Intel Registry

After the research pipeline produces a company dossier and places it in `public/data/intel/`, run the registry script to make it available in the frontend navigation and globe:

```bash
python scripts/register_intel.py
```

**What the script does:**
1. Scans all `public/data/intel/*.json` files for company metadata
2. Extracts `company`, `website`, `ticker`, `sector`, `description`, and `offices` from each dossier
3. Writes a consolidated `src/data/companies.json` — the single source consumed by
   the company selector dropdown and the 3D globe's initial node layout
4. The globe renders offices from every registered company immediately, even before
   the user triggers a live research run

**When to run:** Every time a new intel JSON file is placed in `public/data/intel/`.
The script is idempotent — it always rebuilds from scratch by scanning the directory.

**Adding a company manually:** Drop a properly structured JSON intel file into
`public/data/intel/` and re-run the registry. The script handles malformed files
individually without crashing the entire registration.

### Cross-Company Analysis Generator

Aggregates all registered intel files into the three cross-company views shown in
the Global Strategy Hub (accessible via the "Global Strategy" button in the header):

```bash
python scripts/generate_analysis.py
```

**What the script does:**
1. Loads every intel file from `public/data/intel/` and builds three analysis files:

   **Value Chain Matrix** (`public/data/research/chain_matrix.json`) — Maps
   buyer-supplier dependencies by resolving supply chain and customer concentration
data from each dossier. Normalises company names through a manual alias table
(e.g., "TSMC" → "TSM") and parses revenue share percentages (including projected
ranges like "11-15% (Proj.)") to assign dependency strength.

   **Macro Risk Convergence** (`public/data/research/risk_convergence.json`) —
   Aggregates geopolitical risks by geographic region. Companies contributing to
   the same region are merged; risk scores are normalised to a 0-10 scale and
   dimensions (e.g., "Regulatory", "Trade Restrictions") are collected for each
   region.

   **Chokepoint Analysis** (`public/data/research/chokepoint_analysis.json`) —
   Programmatically identifies critical infrastructure bottlenecks by matching
   supply chain entries against known chokepoints (TSMC Hsinchu Hub, ASML EUV
   Monopsony). Each chokepoint lists the exposed companies and its geographic
   coordinates.

2. All three files carry a `lastUpdated` ISO timestamp for staleness tracking

**When to run:** After registering new intel or updating existing dossiers.
The generator always processes every registered company — incremental rebuild
is handled by the glob-based load (it loads whatever is on disk).

### Institutional Holdings Data

The system displays top-10 institutional holders for each tracked company, sourced from SEC 13F filings. The data is generated by:

```bash
npm run update-holdings
```

or directly:
```bash
python3 scripts/fetch_13f_holdings.py
```

**What the script does:**
1. Fetches CIK→ticker mappings from SEC EDGAR
2. For each of the 20+ major institutional managers (Vanguard, BlackRock, State Street, Fidelity, etc.), resolves their SEC CIK and fetches the latest 13F-HR filing
3. Parses each manager's XML info table (namespace-aware, 
   `informationtable` schema) and extracts holdings for all 11 tracked companies
4. Aggregates by institution, sorts by value descending, takes top 10 per company
5. Computes ownership % against known shares outstanding
6. Writes to `src/data/institutional_holders.json` — the single source consumed by
   both the per-company IntelPanel and the global Holdings tab

**When to run:** Quarterly, after the SEC 13F filing deadline (45 days after quarter-end).
All 13F filings are publicly available via SEC EDGAR with no API key required.

**Adding a new manager:** Add an entry with name and CIK to the `MAJOR_MANAGERS` list
in `scripts/fetch_13f_holdings.py`. SEC CIKs for investment managers are 6-7 digit
numbers that never change. Verify by checking `https://data.sec.gov/submissions/CIK{10-digit}.json`
returns a 200 with `"name"` matching the manager.

**Updating shares outstanding:** Update the `SHARES_OUTSTANDING` dict at the top of
the script. The values come from each company's latest 10-Q/10-K cover page under
"Entity Common Stock, Shares Outstanding".

## License

© 2026 Dossigraphica Project. Built for strategic analysis and geographic visualisation.
Data sources: Brave Search, Jina Reader, SEC filings, public reports.
