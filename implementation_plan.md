# Local Deep Research Agent — Implementation Plan

## Overview

Build a **fully local, zero-cost, autonomous deep research pipeline** that replaces the current manual JSON/Markdown creation workflow (`scripts/register_intel.py` + hand-authored `public/data/intel/*.json` + `public/data/research/*.md`) with an **automated agent** that:

1. Accepts a company ticker/name as input (use the geo-intelligence-extraction-prompt-instructions.md prompt to generate the research as default instructions)
2. Plans multi-hop search queries via a local reasoning LLM
3. Searches the live web via a self-hosted SearXNG instance
4. Scrapes and distills web content into token-efficient Markdown
5. Reflects on knowledge gaps and recurses until satisfied
6. Synthesizes a **structured `GeoIntelligence` JSON** (matching `src/types.ts`) + a **narrative Markdown report** (use the geo-intelligence-extraction-prompt-output_format.md to guide the structured output for the JSON and the narrative report)
7. Writes the results directly to `public/data/intel/{TICKER}.json` and `public/data/research/{TICKER}.md`

The pipeline runs entirely on the local RTX 3070 (8GB VRAM) + 24GB system RAM.

---

## User Review Required

> [!IMPORTANT]
> **Hardware Assumption**: This plan targets your RTX 3070 (8GB VRAM). The recommended model is **Gemma 4 e2b** (~5.5GB VRAM at Q4) for JSON-strict tool execution, with **DeepSeek-R1-Distill-Qwen-7B** (~4.3GB at Q4) as the reasoning/reflection model. Only one model is loaded at a time to stay within your VRAM budget.

> [!WARNING]
> **Docker Requirement**: SearXNG runs in Docker. If Docker is not available/desired, a DuckDuckGo HTML fallback is included in the plan as a zero-config alternative.

> [!IMPORTANT]
> **Architecture Decision**: This plan creates a standalone **Node.js CLI tool** (`scripts/research-agent/`) rather than a persistent backend server. This aligns with the existing `scripts/` pattern (`generate_analysis.py`, `register_intel.py`) and avoids adding backend complexity to the Vite frontend. You invoke it like: `npx tsx scripts/research-agent/run.ts --ticker NVDA`.

---

## Proposed Changes

### Phase 0: Infrastructure Prerequisites

These are one-time setup steps, not code changes.

#### 0.1 — Install & Configure Ollama

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the two target models (only one loaded at a time)
ollama pull gemma4:e2b        # ~5.5GB — JSON-strict tool execution
ollama pull deepseek-r1:7b    # ~4.3GB — reasoning/reflection
```

**Ollama configuration** (set in `~/.ollama/config` or env vars):
- `OLLAMA_NUM_PARALLEL=1` — Force sequential inference to protect VRAM
- Default `num_gpu` — Let Ollama auto-detect layers for the 3070

#### 0.2 — Deploy SearXNG via Docker

```yaml
# docker-compose.yml (placed at project root or ~/searxng/)
version: '3.8'
services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./searxng-config:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080
    restart: unless-stopped
```

**Critical `settings.yml` modifications** (in `searxng-config/`):
```yaml
search:
  formats:
    - html
    - json        # ← MUST enable JSON API
server:
  limiter: false  # ← Disable rate limiting for agent loops
```

#### 0.3 — Install Node.js Dependencies

```bash
npm install ollama zod zod-to-json-schema @mozilla/readability jsdom turndown
npm install -D @types/jsdom @types/turndown
```

---

### Phase 1: Core Pipeline Engine

#### [NEW] `scripts/research-agent/config.ts`

Global configuration constants:

```
- OLLAMA_BASE_URL: "http://localhost:11434"
- SEARXNG_BASE_URL: "http://localhost:8080"
- REASONING_MODEL: "deepseek-r1:7b"
- STRUCTURED_MODEL: "gemma4:e2b"
- MAX_ITERATIONS: 3
- MAX_URLS_PER_QUERY: 5
- MAX_SEARCH_QUERIES: 5
- MAX_CONTEXT_TOKENS: 6000 (approximate)
- OUTPUT_INTEL_DIR: "public/data/intel"
- OUTPUT_RESEARCH_DIR: "public/data/research"
```

---

#### [NEW] `scripts/research-agent/state.ts`

The persistent research state interface (the single object passed through all nodes):

```typescript
interface ResearchState {
  // Input
  ticker: string;
  companyName: string;
  userQuery: string;     // Auto-generated: "Generate a comprehensive GeoIntelligence dossier for {ticker}"

  // Planning
  researchPlan: string;
  searchQueries: string[];

  // Data accumulation
  rawExtractedData: ExtractedFact[];  // Array of {fact, sourceUrl, sourceTitle}
  scrapedUrls: Set<string>;          // Deduplication tracker

  // Control flow
  iterationCount: number;
  isComplete: boolean;
  knowledgeGaps: string[];

  // Output
  finalIntelJson: GeoIntelligence | null;
  finalReportMarkdown: string | null;
}
```

---

#### [NEW] `scripts/research-agent/schemas.ts`

Zod schemas for every LLM-facing node output, enforcing deterministic JSON:

| Schema | Purpose | Key Fields |
|--------|---------|------------|
| `PlannerOutputSchema` | Planner node output | `researchPlan: string`, `searchQueries: string[]` |
| `ReflectorOutputSchema` | Reflector node output | `isComplete: boolean`, `knowledgeGaps: string[]`, `newSearchQueries: string[]` |
| `FactExtractionSchema` | Synthesizer node output | `facts: {claim: string, sourceUrl: string}[]` |
| `GeoIntelligenceSchema` | Final publisher output | Mirrors the full `GeoIntelligence` type from `src/types.ts` |

All schemas are converted to JSON Schema via `zod-to-json-schema` and passed to Ollama's `format` parameter for constrained decoding.

---

#### [NEW] `scripts/research-agent/nodes/planner.ts`

**Node 1 — Strategy Planner**
- **Model**: `deepseek-r1:7b` (reasoning model)
- **Input**: `state.userQuery` + `state.ticker`
- **Output**: Updates `state.researchPlan` and `state.searchQueries` (3–5 queries)
- **Prompt Architecture**: Declarative boundaries, not step-by-step. Instructs the model to generate specific search queries covering: offices/facilities, revenue geography, supply chain, customers, geopolitical risks, expansion/contraction signals.
- **`<think>` tag handling**: Custom interceptor strips `<think>...</think>` before JSON.parse()

---

#### [NEW] `scripts/research-agent/nodes/searcher.ts`

**Node 2 — Parallel Search**
- **Model**: None (pure HTTP)
- **Input**: `state.searchQueries`
- **Output**: Array of `{url, title, snippet}` per query
- **Implementation**: `Promise.allSettled()` dispatching HTTP GET to `http://localhost:8080/search?q={query}&format=json`
- **Deduplication**: Skips URLs already in `state.scrapedUrls`; discards duplicate domains
- **Fallback**: If SearXNG is unreachable, falls back to DuckDuckGo HTML scraping via `https://html.duckduckgo.com/html/?q={query}`

---

#### [NEW] `scripts/research-agent/nodes/scraper.ts`

**Node 3 — Fetch & Scrape**
- **Model**: None (pure Node.js)
- **Input**: Array of URLs from searcher
- **Output**: Array of `{url, title, markdownContent}`
- **Implementation**:
  1. `fetch()` with timeout (10s) and User-Agent header
  2. Parse HTML with `JSDOM`
  3. Extract article content with `@mozilla/readability`
  4. Convert to Markdown with `TurndownService`
- **Error handling**: Circuit breaker — failed URLs are logged and skipped, never crash the pipeline
- **Concurrency**: `Promise.allSettled()` with max 3 concurrent fetches

---

#### [NEW] `scripts/research-agent/nodes/synthesizer.ts`

**Node 4 — Context Compression (Recursive Summarization)**

This is the critical VRAM defense node.

- **Model**: `gemma4:e2b` (structured output model)
- **Input**: Individual Markdown articles from scraper
- **Output**: Dense `ExtractedFact[]` per article
- **Process**: Each article is individually fed to the LLM with a highly constrained prompt:
  > *"Extract ONLY hard facts relevant to {ticker}'s geographic intelligence: office locations with coordinates, revenue figures by region, supply chain entities with cities/countries, customer names and revenue shares, geopolitical risks with risk scores, expansion/contraction signals. Discard all narrative. Append the source URL to each fact."*
- **Compression target**: 4,000-token article → ~200-token bulleted summary
- **VRAM safety**: Articles are processed **sequentially** (one at a time), never batched

---

#### [NEW] `scripts/research-agent/nodes/reflector.ts`

**Node 5 — Knowledge Gap Evaluator**
- **Model**: `deepseek-r1:7b` (reasoning model)
- **Input**: `state.rawExtractedData` + `state.userQuery`
- **Output**: Updates `state.isComplete`, `state.knowledgeGaps`, generates new `searchQueries` if gaps exist
- **Prompt Architecture**: Acts as adversarial judge evaluating data against a checklist:
  - ☐ Offices with lat/lng coordinates?
  - ☐ Revenue breakdown by region with percentages?
  - ☐ Supply chain entities with criticality ratings?
  - ☐ Customer concentration with revenue shares?
  - ☐ Geopolitical risks with risk scores (1-5)?
  - ☐ Expansion/contraction signals with sources?
- **Routing logic**: If `isComplete === false` AND `iterationCount < MAX_ITERATIONS`, generate 3 new targeted queries and restart from the Planner

---

#### [NEW] `scripts/research-agent/nodes/publisher.ts`

**Node 6 — Final Report Generator**
- **Model**: `gemma4:e2b` (structured output model)
- **Input**: Complete `state.rawExtractedData` array
- **Two-pass output**:
  1. **Pass 1 — Structured JSON**: Generate `GeoIntelligence` JSON matching the Zod schema (constrained decoding via `format` parameter). Write to `public/data/intel/{TICKER}.json`.
  2. **Pass 2 — Narrative Markdown**: Generate the ~5000-word research report with inline citations. Write to `public/data/research/{TICKER}.md`.
- **Post-processing**: Auto-run `scripts/register_intel.py` and `scripts/generate_analysis.py` to refresh the master company list and cross-company analysis.

---

#### [NEW] `scripts/research-agent/utils/think-interceptor.ts`

Utility function to strip `<think>...</think>` tags from DeepSeek-R1 responses before JSON parsing:

```typescript
function extractJsonFromReasoning(raw: string): string {
  const thinkClose = raw.lastIndexOf('</think>');
  if (thinkClose !== -1) {
    return raw.slice(thinkClose + '</think>'.length).trim();
  }
  return raw.trim();
}
```

---

#### [NEW] `scripts/research-agent/utils/searxng-fallback.ts`

DuckDuckGo HTML fallback for when SearXNG is unavailable.

---

#### [NEW] `scripts/research-agent/pipeline.ts`

The main orchestration loop (LangGraph-style state machine):

```
┌──────────────────────────────────────────────────────────────┐
│                     PIPELINE FLOW                            │
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌─────────┐   ┌───────────┐ │
│  │ Planner  │──▶│ Searcher │──▶│ Scraper │──▶│Synthesizer│ │
│  └──────────┘   └──────────┘   └─────────┘   └─────┬─────┘ │
│       ▲                                             │       │
│       │         ┌───────────┐                       │       │
│       └─────────│ Reflector │◀──────────────────────┘       │
│    (if gaps     └─────┬─────┘                               │
│     remain)           │                                      │
│                       ▼ (if complete)                        │
│                 ┌───────────┐                                │
│                 │ Publisher │──▶ .json + .md output          │
│                 └───────────┘                                │
└──────────────────────────────────────────────────────────────┘
```

**Key implementation details:**
- State is a plain object, mutated in-place by each node
- Loop guard: Hard cap at `MAX_ITERATIONS = 3`
- Console logging: Rich progress output (emoji-prefixed) for each phase
- Total estimated execution time: 3–8 minutes per company (depending on model speed and web scraping)

---

#### [NEW] `scripts/research-agent/run.ts`

CLI entry point:

```bash
npx tsx scripts/research-agent/run.ts --ticker NVDA
npx tsx scripts/research-agent/run.ts --ticker AAPL --model gemma4:e2b
npx tsx scripts/research-agent/run.ts --ticker TSM --max-iterations 2
```

Parses CLI args, initializes state, runs the pipeline, writes output files.

---

### Phase 2: Integration Helpers (Optional Future Work)

These are **not** part of the initial implementation but are documented for planning:

#### Frontend Streaming UI
- Add a "Deep Research" button to the Header or IntelPanel
- Create a WebSocket/SSE connection to a lightweight Express server
- Stream pipeline status updates to the UI in real-time
- This requires adding a backend — deferred to Phase 2

#### Batch Mode
```bash
npx tsx scripts/research-agent/run.ts --batch NVDA,AAPL,MSFT,TSM
```
Sequential processing (only one model loaded at a time).

---

## File Summary

| File | Status | Description |
|------|--------|-------------|
| `scripts/research-agent/config.ts` | [NEW] | Configuration constants |
| `scripts/research-agent/state.ts` | [NEW] | ResearchState interface + factory |
| `scripts/research-agent/schemas.ts` | [NEW] | Zod schemas for all LLM outputs |
| `scripts/research-agent/nodes/planner.ts` | [NEW] | Strategy planning node |
| `scripts/research-agent/nodes/searcher.ts` | [NEW] | Web search node (SearXNG + fallback) |
| `scripts/research-agent/nodes/scraper.ts` | [NEW] | HTML→Markdown extraction node |
| `scripts/research-agent/nodes/synthesizer.ts` | [NEW] | Context compression node |
| `scripts/research-agent/nodes/reflector.ts` | [NEW] | Knowledge gap evaluation node |
| `scripts/research-agent/nodes/publisher.ts` | [NEW] | Final JSON + MD generation node |
| `scripts/research-agent/utils/think-interceptor.ts` | [NEW] | DeepSeek `<think>` tag handler |
| `scripts/research-agent/utils/searxng-fallback.ts` | [NEW] | DuckDuckGo HTML fallback |
| `scripts/research-agent/pipeline.ts` | [NEW] | Main orchestration state machine |
| `scripts/research-agent/run.ts` | [NEW] | CLI entry point |
| `docker-compose.searxng.yml` | [NEW] | SearXNG Docker Compose file |
| `searxng-config/settings.yml` | [NEW] | SearXNG configuration |
| `package.json` | [MODIFY] | Add `ollama`, `jsdom`, `readability`, `turndown` deps + `research` script |

---

## Open Questions

> [!IMPORTANT]
> **Q1: CLI vs Server?** This plan proposes a CLI tool matching the existing `scripts/` pattern. A frontend-integrated version with streaming UI would require adding Express/WebSocket backend. Do you prefer CLI-first, or should we build the server from the start?

> [!IMPORTANT]
> **Q2: Model preference?** The plan defaults to Gemma 4 E2B + DeepSeek-R1 7B. If you have different models already pulled in Ollama, or prefer a single-model approach (e.g., Gemma 4 only), the plan can be adjusted.

> [!IMPORTANT]
> **Q3: Docker availability?** Is Docker installed and available? If not, the plan will default to the DuckDuckGo HTML fallback for search and skip the SearXNG setup.

---

## Verification Plan

### Automated Tests
1. **Unit test schemas**: Validate that sample JSON payloads pass all Zod schemas
2. **Pipeline integration test**: Run the full pipeline for a known ticker (e.g., `NVDA`) and verify:
   - `public/data/intel/NVDA.json` is valid JSON matching `GeoIntelligence` schema
   - `public/data/research/NVDA.md` contains expected sections
   - `src/data/companies.json` is updated after `register_intel.py` runs
3. **VRAM monitoring**: Run `nvidia-smi` during pipeline execution to verify VRAM stays under 7.5GB

### Manual Verification
1. Run `npm run dev` and confirm the newly generated company appears on the globe
2. Click on the company node and verify the IntelPanel displays the JSON data correctly
3. Open the research markdown and confirm citations and formatting
