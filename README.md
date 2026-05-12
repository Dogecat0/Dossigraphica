# Dossigraphica: Geographic Intelligence Dashboard

**[Dossigraphica](https://zhicheng-wang.com/Dossigraphica/)** is a high-fidelity Geographic Intelligence (GEOINT) visualization platform designed for corporate analysis. It provides a "Parchment and Ink" styled 3D interface to explore the global footprint, supply chain dependencies, and geopolitical risk profiles of major multinational corporations.

It features a local-first, autonomous Geo-Intelligence research agent pipeline. A user submits a query, and the pipeline searches the web, extracts content, and reasons over it to produce structured intelligence briefs and Markdown narratives, streamed via SSE (ready for UI integration).

## 🌍 Key Features

- **Interactive 3D Globe:** High-fidelity visualization of global assets using `react-globe.gl` and Three.js, featuring office hubs, supply chain arcs, and risk hotspots.
- **Global Strategy Hub:** Integrated dashboards for cross-company analysis:
    - **Value Chain Matrix:** Visualizing buyer-supplier dependencies and equipment provider links.
    - **Macro Risk Convergence:** Aggregating geopolitical risks across regions to identify systemic threats.
    - **Chokepoint Analysis:** Identifying critical infrastructure and geographic bottlenecks (foundries, shipping lanes, regional hubs).
- **Autonomous Research Agent:** A multi-stage Python pipeline that executes a deterministic research workflow:
    1.  **Planning:** Generating targeted search queries.
    2.  **Searching:** Braving Discovery API for broad web coverage.
    3.  **Extraction & Sieve:** Jina Reader API for markdown extraction followed by Map-Reduce summarization.
    4.  **Entity Assembly:** Structured gap detection and geographic data synthesis.
    5.  **Enrichment:** Targeted secondary research to fill detected data gaps.
    6.  **Drafting:** Parallel generation of structured JSON intel and rich Markdown dossiers.
- **Adaptive LLM Engine:** Supports Gemini (Current active), Local (llama.cpp), and Featherless providers with intelligent token management and multi-shot generation for complex schemas.
- **Deep-Dive Dossiers:** Integrated research panels featuring detailed Markdown reports and structured intelligence data.
- **Parchment Aesthetic:** A unique, professional visual style inspired by classic cartography and modern intelligence briefs.

## 🛠️ Tech Stack

### Frontend UI
- **Framework:** React 19, TypeScript, Vite
- **Styling:** Tailwind CSS 4 (using modern CSS variables and primitives)
- **State Management:** Zustand 5
- **Visualization:** [react-globe.gl](https://github.com/vasturiano/react-globe.gl), Three.js, Lucide-React
- **Content:** React-Markdown with Rehype-Raw and Remark-GFM

### Research Agent (Python Sidecar)
- **API Engine:** FastAPI (SSE Streaming endpoint)
- **Orchestration:** Async generators driving a multi-phase Research Pipeline
- **Inference Client:** LiteLLM for multi-provider support (Local, Gemini, Featherless)
- **Structured Generation:** Pydantic for schema validation, `json-repair` for robustness
- **Search & Extraction:** Brave Search API & Jina Reader API
- **Local LLM Server:** `llama.cpp` server (via Docker Compose)

## 📁 Project Structure

```text
├── docker-compose.yaml      # LLM infrastructure (llama.cpp server)
├── public/data/             # Intelligence data & research reports cache
│   ├── intel/               # Per-company JSON intelligence files
│   ├── research/            # Per-company Markdown reports & global analysis
│   └── countries.json       # GeoJSON for global boundaries
├── python-sidecar/          # Autonomous research pipeline (FastAPI)
│   ├── main.py              # FastAPI entry point
│   ├── pipeline.py          # Research Orchestrator (Orchestration Engine)
│   ├── llm.py               # Adaptive LLM Client (Map-Reduce & Multi-shot)
│   ├── schemas.py           # Pydantic models for GEOINT schema
│   ├── tasks/               # Pipeline stages (planner, extractor, assembly, etc.)
│   └── utils/               # IO Cache, Log Replay, and Geocoding fallbacks
├── scripts/                 # Data synchronization and analysis scripts
│   ├── register_intel.py    # Synchronizes per-company intel to the main registry
│   └── generate_analysis.py # Aggregates global analysis (Chain Matrix, Risks)
├── src/                     # Frontend UI application
│   ├── components/          # React components (Globe, IntelPanel, GlobalPanel)
│   ├── useGeoIntel.ts       # Centralized Zustand store
│   └── types.ts             # TypeScript definitions for the GEOINT schema
└── vite.config.ts           # Vite configuration with /Dossigraphica/ base path
```

## 🚀 Getting Started

### Prerequisites

- **Node.js:** v20 or higher
- **Python:** v3.10 or higher
- **Docker:** (For local inference engine)
- **Environment Variables:** Set in `.env` (copy from `.env.example` if available)
    - `BRAVE_SEARCH_API_KEY`: For web research.
    - `HF_TOKEN`: To download models for llama.cpp.
    - `GEMINI_API_KEY`: (Optional) For using Gemini as the research engine.

### Installation

1.  **Clone and Install Frontend Dependencies:**
    ```bash
    npm install
    ```

2.  **Setup Python Environment:**
    ```bash
    cd python-sidecar
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cd ..
    ```

### Development

The application requires running multiple services locally:

1.  **Start the Local LLM Server:**
    ```bash
    docker-compose up -d
    ```

2.  **Run the Research Pipeline Backend:**
    ```bash
    cd python-sidecar
    source .venv/bin/activate
    uvicorn main:app --reload --port 8000
    ```

3.  **Run the Vite Frontend:**
    In a new terminal:
    ```bash
    npm run dev
    ```

## 📊 Data Management

The dashboard leverages pre-generated data and the live research pipeline:

1.  **Register New Intel:** After dropping or generating `.json` files in `public/data/intel/`, sync the registry:
    ```bash
    python scripts/register_intel.py
    ```

2.  **Generate Global Analysis:** Aggregate cross-company data into the strategy hub:
    ```bash
    python scripts/generate_analysis.py
    ```

## 📝 License

© 2026 Dossigraphica Project. Built for strategic analysis and geographic visualization.
Data sources: OpenStreetMap, SEC Filings (simulated), Brave Search, and public reports.
