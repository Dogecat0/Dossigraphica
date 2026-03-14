# Dossigraphica: Geographic Intelligence Dashboard

**Dossigraphica** is a high-fidelity Geographic Intelligence (GEOINT) visualization platform designed for corporate analysis. It provides a "Parchment and Ink" styled 3D interface to explore the global footprint, supply chain dependencies, and geopolitical risk profiles of major multinational corporations.

![Dossigraphica Preview](public/vite.svg) *Note: Replace with actual screenshot for production.*

## 🌍 Key Features

- **Interactive 3D Globe:** High-performance visualization of global assets using `react-globe.gl` and Three.js.
- **Multi-Layer Intelligence:** Toggle between different strategic layers:
    - **Corporate Footprint:** Headquarters, regional hubs, R&D centers, and logistics nodes.
    - **Supply Chain Mapping:** Tier-1 suppliers, foundries, and contract manufacturers with criticality ratings.
    - **Customer Concentration:** Geographic revenue distribution and key customer hubs.
    - **Geopolitical Risk:** Real-time (simulated) monitoring of regional conflicts, regulatory hurdles, and infrastructure threats.
- **Deep-Dive Dossiers:** Integrated research panels featuring detailed Markdown reports and structured intelligence data.
- **Automated Data Pipeline:** Python-based geocoding scripts to transform raw office addresses into geolocated JSON assets.
- **Parchment Aesthetic:** A unique, professional visual style inspired by classic cartography and modern intelligence briefs.

## 🛠️ Tech Stack

- **Frontend:** React 19, TypeScript, Vite
- **Styling:** Tailwind CSS 4 (Vanilla CSS variables & modern primitives)
- **State Management:** Zustand
- **Visualization:** [react-globe.gl](https://github.com/vasturiano/react-globe.gl), Three.js
- **Content:** React-Markdown with Rehype-Raw for rich research reports
- **Scripts:** Python 3 with `geopy` for batch geocoding

## 📁 Project Structure

```text
├── public/data/            # Intelligence data & research reports
│   ├── intel/              # Structured GEOINT JSON files (AMZN, MSFT, etc.)
│   └── research/           # Markdown-based narrative analysis
├── scripts/                # Data processing and geocoding scripts
├── src/
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
- **Python:** v3.9 or higher (for data scripts)

### Installation

1.  **Clone and Install Dependencies:**
    ```bash
    npm install
    ```

2.  **Setup Python Environment (Optional, for scripts):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install geopy
    ```

### Development

Run the Vite development server:
```bash
npm run dev
```

### Data Management

The dashboard follows an **Intel-First** workflow. The global company list and map are automatically synchronized from your research reports.

1.  **Add Research:** Drop Gemini-generated `.json` and `.md` reports into:
    -   `public/data/intel/`
    -   `public/data/research/`
2.  **Synchronize Registry:**
    ```bash
    python scripts/register_intel.py
    ```
    *This automatically builds `src/data/companies.json` from your intel files.*

*(Legacy: If you only have raw addresses without coordinates, you can still use `scripts/geocode.py` to process `scripts/offices_input.csv`.)*

## 📝 License

© 2026 Dossigraphica Project. Built for strategic analysis and geographic visualization.
Data sources: OpenStreetMap, SEC Filings (simulated), and Geopolitical Intelligence Reports.
