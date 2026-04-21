# Dossigraphica: Geographic Intelligence Dashboard

**Dossigraphica** is a high-fidelity Geographic Intelligence (GEOINT) visualization platform designed for corporate analysis. It provides a "Parchment and Ink" styled 3D interface to explore the global footprint, supply chain dependencies, and geopolitical risk profiles of major multinational corporations.

It features a local-first, autonomous Geo-Intelligence research agent pipeline. A user submits a query, and the pipeline searches the web, extracts content, and reasons over it to produce structured intelligence briefs and Markdown narratives, streamed via SSE (ready for UI integration).

## 🌍 Key Features

- **Interactive 3D Globe:** Visualization of global assets using `react-globe.gl` and Three.js.
- **Autonomous Research Agent:** Python-based sidecar executing a deterministic, multi-stage data gathering and intelligence drafting pipeline.
- **Multi-Layer Intelligence:** Toggle between different strategic layers:
    - **Corporate Footprint:** Headquarters, regional hubs, R&D centers, and logistics nodes.
    - **Supply Chain Mapping:** Tier-1 suppliers, foundries, and contract manufacturers with criticality ratings.
    - **Customer Concentration:** Geographic revenue distribution and key customer hubs.
    - **Geopolitical Risk:** Monitoring of regional conflicts, regulatory hurdles, and infrastructure threats.
- **Deep-Dive Dossiers:** Integrated research panels featuring detailed Markdown reports and structured intelligence data (backend supports real-time streaming).
- **Parchment Aesthetic:** A unique, professional visual style inspired by classic cartography and modern intelligence briefs.

## 🛠️ Tech Stack

### Frontend UI
- **Framework:** React 19, TypeScript, Vite
- **Styling:** Tailwind CSS 4 (Vanilla CSS variables & modern primitives)
- **State Management:** Zustand
- **Visualization:** [react-globe.gl](https://github.com/vasturiano/react-globe.gl), Three.js
- **Content:** React-Markdown with Rehype-Raw for rich research reports

### Research Agent (Python Sidecar)
- **API Engine:** FastAPI (SSE Streaming endpoint)
- **Orchestration:** Python `async`/`await` generators driving finite state machine (pipeline steps)
- **Inference Client:** LiteLLM & Pydantic for structured generation, validation, and token chunking
- **Search & Extraction:** Brave Search API & Jina Reader API
- **Local LLM Server:** `ghcr.io/ggml-org/llama.cpp:server-cuda` running Gemma 4 E4B (GGUF via Docker Compose)

## 📁 Project Structure

```text
├── docker-compose.yaml     # LLM infrastructure (llama.cpp server)
├── docs/                   # Documentation and architectural reviews
├── python-sidecar/         # Autonomous research pipeline (FastAPI)
│   ├── main.py             # FastAPI SSE endpoint
│   ├── pipeline.py         # Research Orchestrator FSM
│   ├── tasks/              # Pipeline stages (planner, elicitation, triage, etc.)
│   └── utils/              # Log replay & Geocoder fallback
├── public/data/            # Intelligence data & research reports cache
├── scripts/                # Data processing and geocoding scripts
├── src/                    # Frontend UI application
│   ├── components/         # React UI components (Globe, IntelPanel, etc.)
│   ├── data/               # Generated company office data
│   ├── utils/              # Helper functions
│   ├── types.ts            # TypeScript definitions for the GEOINT schema
│   └── useGeoIntel.ts      # Zustand store for global application state
└── index.html              # Entry point
```

## 🚀 Getting Started

### Prerequisites

- **Node.js:** v18 or higher
- **Python:** v3.10 or higher
- **Docker:** (For local inference engine)
- **Environment Variables:** `BRAVE_SEARCH_API_KEY` and `HF_TOKEN` (to download models) set in `.env`

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
    *(Alternatively, test the pipeline headless using `python test_run.py`)*

3.  **Run the Vite Frontend:**
    In a new terminal:
    ```bash
    npm run dev
    ```

### Data Management

The dashboard uses the Python sidecar to generate intel dynamically. However, existing datasets can be managed manually:
- Drop `.json` and `.md` reports directly into `public/data/intel/` and `public/data/research/`.
- Synchronize registry via `python scripts/register_intel.py`.

## 📝 License

© 2026 Dossigraphica Project. Built for strategic analysis and geographic visualization.
Data sources: OpenStreetMap, SEC Filings (simulated), and publicly available reports.
