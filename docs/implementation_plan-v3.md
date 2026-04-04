# Local Deep Research Agent (v3) — Implementation Plan

Provide an architectural implementation plan to migrate and execute the Local Deep Research pipeline. As documented in the v3 architecture brief, this approach moves orchestration and memory management natively to a Python FastAPI sidecar, resolving inherent Node.js/V8 LLM memory leakage issues.

## User Review Required

> [!WARNING]
> This plan supersedes the previous pure-TypeScript architecture. The orchestration, state management, and reasoning loops will now run entirely in Python. TypeScript will be purely a frontend consumer via Server-Sent Events (SSE).

> [!IMPORTANT]
> **Architecture Finalization:** 
> 1. **Zero LangChain/LangGraph:** The state machine and graph routing will be written in **pure Python** (standard control flow, `while` loops, and `async` generators), ensuring zero dependency bloat from LangChain/LangGraph.
> 2. **Tavily API:** Will be used for Managed Extraction. 
> 3. **Standalone `llama.cpp`:** We will use a standard `llama.cpp` HTTP server (OpenAI-compatible) rather than Ollama or direct Python bindings. 
> 4. **Pydantic Validation:** The Python sidecar will use `outlines` (or `instructor` via OpenAI spec) to bind Pydantic schemas and ensure deterministic JSON from the `llama.cpp` server. 
> 
> Please verify these final details and reply with an explicit **"Approved"** or **"Go ahead"** so we can begin coding.

## Proposed Changes

### Full Pipeline Implementation

We will accomplish everything in multiple implementation phases, maintaining logical dependencies.

#### Phase 1. Python Inference Sidecar & Environment
- **[NEW] `python-sidecar/` directory**: Establish a new module within the repository.
- **[NEW] `python-sidecar/requirements.txt`**: Core dependencies: `fastapi`, `uvicorn`, `pydantic`, `outlines`, `sse-starlette`, and `openai` (for communicating with `llama.cpp` server API). *No LangGraph or LangChain.*
- **[NEW] `python-sidecar/main.py`**: The FastAPI application entry point, exposing an endpoint (e.g. `POST /api/research`) that receives the research target and starts the pure Python asynchronous pipeline, returning an `EventSourceResponse` (SSE stream).

#### Phase 2. Deterministic State & Schemas (Module F)
- **[NEW] `python-sidecar/schemas.py`**: Pydantic definitions strictly mapping the research requirements. 
  - `ResearchState`: The in-memory, ephemeral state class containing the scratchpad, extracted facts, URLs, and orchestration flags.
  - `PlannerSchema`: Forces the Reasoning First structure.
  - `ElicitationSchema`: The structure handling the "Is That All?" protocol.
  - `GeoIntelligenceSchema`: The target JSON output format mirroring the TS frontend shapes.
- **[NEW] `python-sidecar/llm.py`**: Client wrappers for interacting with the `llama.cpp` server. Will utilize `outlines`/`instructor` mapped to Pydantic schemas to enforce token-perfect JSON extraction natively.

#### Phase 3. Core Intelligence Tasks
Since we are using pure Python, these will be standalone `async` functions rather than "nodes":
- **[NEW] `python-sidecar/tasks/planner.py`:** Initiates the Strategy Planner via the reasoning model. Outputs initial queries.
- **[NEW] `python-sidecar/tasks/elicitation.py`:** The Exhaustive Elicitation loop. Evaluates Planner queries, demanding 3+ distinct additions until `is_exhausted` is hit.
- **[NEW] `python-sidecar/tasks/search.py`:** Calls the local SearXNG Docker container via HTTP. Returns URLs and snippets.
- **[NEW] `python-sidecar/tasks/triage.py`:** Evaluates SearXNG snippets to rank top URLs via `llama.cpp`.
- **[NEW] `python-sidecar/tasks/extractor.py`:** Managed extraction utilizing the **Tavily API** to grab raw markdown from targets.
- **[NEW] `python-sidecar/tasks/synthesizer.py`:** Context Squeezing/Usefulness Filter. Distills massive markdown blobs into hardcore facts natively.
- **[NEW] `python-sidecar/tasks/reflector.py`:** Evaluates the `scratchpad` against task complete criteria. Identifies gaps for the next loop.
- **[NEW] `python-sidecar/tasks/drafter.py`:** Iterative drafting to emit the final Markdown report and structured JSON dictionary.

#### Phase 4. Pure Python Orchestration Engine
- **[NEW] `python-sidecar/pipeline.py`:** A dedicated state machine orchestrator running a strict `while` loop (the Ralph Loop). It sequentially awaits the task functions, manually handles conditional edge logic (checking `state.is_complete` and `nudge_count`), and `yields` JSON dictionaries to act as the raw Server-Sent Event stream for the UI.

#### Phase 5. Presentation Layer Handoff (TypeScript UI)
- **[MODIFY] Vite App / TS Frontend**: Create a frontend view or CLI wrapper to interact with the Python server.
- **[NEW] `src/services/ResearchClient.ts`**: A dedicated API client that consumes the FastAPI SSE streams, handling UI updates dynamically.

## Verification Plan

### Automated Tests
- Schema Validation: Code unit tests validating that the `.json` and `.md` outputs conform seamlessly to the required standards out of the pure Python pipeline.
- State Flow: Execute isolated tests verifying the `pipeline.py` loop cleanly breaks or restarts without Langchain overhead.

### Manual Verification
- Execute a pipeline run against the running FastAPI docker/service from the TS frontend.
- Watch SSE stream payload logs print sequentially all the way to final file generation.
- Monitor VRAM via `nvidia-smi` to ensure the isolated `llama.cpp` server maintains memory within the 8GB budget.
- We have some existing TypeScript code in `scripts/research-agent/`, I assume once the python sidecar is ready we have no use for it and can delete it, validate and proceed.
