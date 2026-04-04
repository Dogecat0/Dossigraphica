# **Architecture and Implementation of a Local Deep Research Agent Pipeline in TypeScript (v3.0)**

**Anchor Date:** April 4, 2026\.

This updated intelligence briefing details the deployment of a highly optimized, hybrid "Deep Research" pipeline. While the primary orchestration remains in TypeScript, this v3.0 architecture introduces a dedicated Python sidecar to manage local Large Language Model (LLM) inference, resolving severe memory leak issues inherent to Node.js environments. Furthermore, it establishes a strict "Intelligence Delegation" framework, routing specific cognitive tasks to specialized model architectures to maximize the capabilities of an 8GB VRAM NVIDIA RTX 3070\.

## 

## **MODULE A: Orchestration and the Python Sidecar Architecture**

Attempting to run complex, multi-model LLM orchestration directly within a Node.js/TypeScript runtime frequently leads to VRAM fragmentation and catastrophic memory leaks. To resolve this, the architecture separates the application into two distinct environments communicating via local REST APIs.

1. **The TypeScript Orchestrator:** The Next.js or Node.js environment acts purely as the central nervous system. It manages the LangGraph Directed Acyclic Graph (DAG), maintains the ResearchState object, coordinates the Ralph Loop (Worker/Quality/Critic), and handles the user interface.  
2. **The Python Inference Sidecar:** A local FastAPI server running directly on the host machine. This sidecar utilizes enterprise-grade Python inference libraries (such as vLLM or an optimized llama.cpp Python binding). The sidecar acts as an abstraction layer; the TypeScript app simply sends a payload requesting "planning," and the Python sidecar handles loading the correct model into VRAM, executing the prompt, enforcing JSON schemas (via the outlines library), and instantly flushing the VRAM upon completion.

## 

## **MODULE B: The Intelligence Delegation Matrix**

Not all tasks within a deep research loop require complex logical reasoning. Utilizing a high-parameter reasoning model to simply rank URLs or extract dates wastes valuable compute cycles. The Python sidecar dynamically swaps models based on the required "IQ" of the specific graph node.

| Cognitive Task | Required Intelligence | Assigned Model | Architectural Justification |
| :---- | :---- | :---- | :---- |
| **Strategy & Planning** | High (Logic/Routing) | **Qwen 3.5 9B** or **Gemma 4 E4B** | These dense models excel at strict JSON compliance, tool calling, and generating comprehensive search strategies. |
| **Fact Extraction** | Low (Reading/Parsing) | **LFM 2.5 (SSM-Hybrid)** | Liquid Foundation Models handle massive context windows (reading scraped articles) with near-zero KV cache bloat, making them perfect for extracting raw data. |
| **Source Ranking** | Low (Evaluation) | **LFM 2.5 (SSM-Hybrid)** | Quickly evaluates the relevance of SearXNG URLs against the user query without bottlenecking the primary reasoning engine. |
| **Reflection & Critique** | High (Analysis) | **Qwen 3.5 9B** or **Gemma 4 E4B** | Acts as the adversarial judge in the Ralph Loop, requiring high logical deduction to identify factual gaps in the scratchpad. |

## 

## **MODULE C: Hybrid Search and Managed Extraction Infrastructure**

To balance cost, speed, and reliability, the data retrieval pipeline utilizes a hybrid approach, separating the *discovery* of information from the *extraction* of information.

* **Zero-Cost Discovery (SearXNG):** The TypeScript orchestrator executes parallel web searches against a local SearXNG Docker container. SearXNG aggregates results from Google, Bing, and academic repositories, returning a JSON payload of URLs and snippets completely free of rate limits or API costs.  
* **Intelligent Source Ranking:** The URLs and snippets are passed to the Python sidecar, where the **LFM 2.5** model rapidly scores them for relevance, filtering out SEO spam or redundant domains.  
* **Managed Extraction (Tavily API):** The highest-ranked URLs are then sent to the Tavily API for extraction. By offloading this specific task to a managed service, the local pipeline avoids the massive compute overhead of running headless browser containers (like Playwright) to bypass Cloudflare protections or render complex JavaScript Single Page Applications (SPAs). Tavily returns the target content as token-efficient, sanitized Markdown.

## **MODULE D: The Asynchronous Research Loop**

The execution flow leverages the LangGraph state machine, coordinated by the TypeScript orchestrator and powered by the Python sidecar.

1. **Hypothesis Generation:** The user submits a query. The TS orchestrator pings the Python sidecar. **Qwen 3.5 9B** generates a structured JSON research plan and an array of search queries.  
2. **Aggregation:** The TS orchestrator queries the local **SearXNG** instance.  
3. **Triage:** The raw search results are passed to **LFM 2.5** via the sidecar to rank the top 5 most authoritative URLs.  
4. **Extraction:** The TS orchestrator calls the **Tavily API** to convert those 5 URLs into clean Markdown.  
5. **Context Squeezing:** The massive Markdown blocks are fed back to **LFM 2.5**. Because it is an SSM-hybrid, it absorbs the 15,000+ tokens without overflowing the 8GB VRAM, extracting only the hard facts and appending them to the persistent LLM scratchpad.  
6. **The Ralph Loop Evaluation:** **Gemma 4 E4B** reviews the scratchpad. If factual gaps exist, it generates new search queries and routes the graph back to Step 2\.  
7. **Iterative Drafting:** Once the data is complete, the Python sidecar utilizes a proxy model approach, iteratively drafting the final comprehensive report section-by-section, ensuring no mid-generation degradation occurs.

You are absolutely right to call this out. This is a well-documented phenomenon known as "generation fatigue" or "early stopping"—especially prevalent in sub-10 billion parameter models. When asked to list *all* facets of a problem or *all* necessary search queries, smaller models will lazily stop after three or four items, assuming the task is complete.

To counteract this, we need to architect a programmatic "nudge" system into the LangGraph state machine. By explicitly challenging the model with an "Is that all?" prompt, we effectively reset its token generation probabilities, forcing it to dig deeper into its latent space or the provided scratchpad.

Here is the architectural addendum incorporating this strategy into our v3.0 pipeline.

---

## **MODULE E: The Exhaustive Elicitation Loop ("Is That All?" Protocol)**

To prevent the Deep Research agent from executing shallow investigations based on lazy, incomplete lists, the LangGraph architecture must implement an **Exhaustive Elicitation Loop** during both the Strategy (Planning) and Synthesizer phases.

Instead of accepting the LLM's first output and immediately moving to the next node, the orchestrator introduces a programmatic friction point designed to squeeze every possible angle out of the model.

### **1\. The Elicitation Node Architecture**

We introduce a new intermediary node within the LangGraph DAG, situated immediately after the *Strategy Planner* and the *Synthesizer*.

When the Planner model (e.g., **Qwen 3.5 9B**) generates its initial JSON array of search\_queries, the state does *not* route directly to the Search Engine. Instead, it routes to the **Elicitation Node**.

### **2\. The Adversarial "Nudge" Prompt**

The Elicitation Node takes the newly generated list, appends it to the user's original query, and fires a secondary, highly adversarial prompt back to the Python sidecar.

The prompt architecture acts as a strict supervisor:

**System:** You are a relentless research director. Review the generated list of search queries against the original prompt.

**Action:** Identify blind spots. Are you absolutely certain this covers every geopolitical, financial, and historical angle? What is missing?

**Constraint:** You must generate at least 3 *additional, distinct* queries that explore tangential or overlooked angles. If you are mathematically certain that every conceivable angle has been covered, output the boolean flag is\_exhausted: true.

### **3\. Zod Schema for the Exhaustion Loop**

To ensure this loop doesn't break the TypeScript parsing logic, the Zod schema utilized by the sidecar during this phase must accommodate both the new data and the termination switch:

TypeScript

const ElicitationSchema \= z.object({

  critique: z.string().describe('Critique of the previous list. What angles were missed?'),

  additional\_items: z.array(z.string()).describe('New items to append to the master list.'),

  is\_exhausted: z.boolean().describe('Set to true ONLY if absolutely no new angles exist.')

});

### **4\. State Merging and The Circuit Breaker**

When the Python sidecar returns this JSON, the TypeScript orchestrator takes the additional\_items array and merges it with the original array in the ResearchState object.

To prevent infinite loops (and to protect the 8GB VRAM compute budget), the LangGraph edge logic evaluates two conditions:

1. **If is\_exhausted is true:** Break the loop and proceed to the next major phase (e.g., executing the searches).  
2. **If is\_exhausted is false AND nudge\_count \< 3:** Increment the counter and loop back to the Elicitation Node to squeeze the model again.  
3. **If nudge\_count reaches 3 (Circuit Breaker):** Forcefully break the loop and proceed.

## **MODULE F: Enforcing Deterministic Outputs via Pydantic and Logit Processors**

With the orchestration layer migrated entirely to Python via the native langgraph package, the fundamental challenge remains: coercing local, sub-10 billion parameter LLMs (like Qwen 3.5 9B or Gemma 4 E4B) into outputting flawless, parseable data structures.

Because the Python backend now directly manages the LLM memory context, we no longer rely on fragile string-parsing or the json\_repair fallback as our primary defense. Instead, the architecture utilizes **Pydantic** in conjunction with the **outlines** library (or the instructor library, if utilizing llama-cpp-python's OpenAI-compatible server). This combination enforces schema compliance at the foundational token-generation level.

### **1\. Defining the State Machine Boundaries (Pydantic)**

Every functional node within the LangGraph DAG that requires structured data must define its exact expected output using Pydantic BaseModel classes.

Crucially, we enforce the **"Reasoning First"** architectural mandate by ensuring the first field in the Pydantic schema always demands the model's internal logic. This drastically reduces hallucinations in smaller models.

Python

from pydantic import BaseModel, Field  
from typing import List

class PlannerSchema(BaseModel):  
    \# Forcing reasoning first prevents structural hallucination  
    reasoning: str \= Field(  
        ...,   
        description="Your step-by-step internal logic evaluating the user query."  
    )  
    search\_queries: List\[str\] \= Field(  
        ...,   
        description="An array of 3 to 5 precise search strings to query the internet."  
    )

class ElicitationSchema(BaseModel):  
    critique: str \= Field(  
        ...,   
        description="Critique of the previous list. What geopolitical angles were missed?"  
    )  
    additional\_items: List\[str\] \= Field(  
        ...,   
        description="New search queries to append to the master list."  
    )  
    is\_exhausted: bool \= Field(  
        ...,   
        description="Set to True ONLY if absolutely no new angles exist."  
    )

### **2\. Token-Level Enforcement via outlines**

Standard JSON prompting relies on the LLM "understanding" the prompt and choosing to output valid JSON. This fails routinely on 8GB hardware.

By integrating Pydantic with a library like outlines (running on top of vLLM or llama.cpp in the Python sidecar), the architecture translates the Pydantic schema into a Regex-based Finite State Machine (FSM). During inference, if the model attempts to generate a token that violates the Pydantic schema (e.g., trying to output conversational text like "Here are your queries:" instead of a {), the logit processor mathematically forces the probability of that invalid token to 0.0.

Python

import outlines  
import outlines.models as models

\# Initialize the local Qwen model within the Python worker thread  
model \= models.transformers("Qwen/Qwen2.5-7B-Instruct", device="cuda")

\# Bind the Pydantic schema directly to the generation engine  
generator \= outlines.generate.json(model, PlannerSchema)

def execute\_planner\_node(state: ResearchState) \-\> dict:  
    prompt \= f"Analyze this query and generate a plan: {state\['user\_query'\]}"  
      
    \# The generator mathematically CANNOT output invalid JSON  
    structured\_output \= generator(prompt)  
      
    \# structured\_output is now a validated Pydantic object  
    return {"search\_queries": structured\_output.search\_queries}

### **3\. The Presentation Layer Handoff (TypeScript)**

Because TypeScript is now strictly relegated to the UI, it requires zero orchestration logic or Zod schemas.

The Python FastAPI backend simply yields the verified Pydantic objects as JSON strings over a Server-Sent Events (SSE) connection or WebSocket. The Next.js frontend receives a continuous, guaranteed-valid stream of data updates (e.g., {"status": "planning", "queries": \[...\]}) and reactively maps them to UI components, creating a beautiful, real-time "thinking" dashboard for the user without ever risking a parsing crash on the client side.

## **MODULE G: In-Memory State Orchestration and LLM-Native Semantic Filtering**

To fulfill the mandate of a completely stateless, zero-database architecture, the Deep Research pipeline must treat the execution of a research task as a single, ephemeral compute lifecycle. From the perspective of the TypeScript Next.js application, the system is a black-box "one-shot" pipeline: the user submits a query, and the application simply awaits the final, comprehensive Markdown report (with optional real-time status streams).

### **1\. The "One-Shot" Presentation Layer (TypeScript)**

The TypeScript frontend initiates the process via a single HTTP POST request (or Server-Sent Events connection) to the Python FastAPI sidecar.

The Python server instantly instantiates a fresh LangGraph `ResearchState` dictionary in the system's RAM. There are no databases, no persistent vector stores, and no file-system caching. If the Python worker crashes or the user closes the connection, the state is naturally garbage-collected by the operating system, ensuring zero memory leak accumulation across sessions. The TS app merely listens to the SSE stream to display UI loading states (e.g., `"Scraping SEC filings..."`) until the final `{"report": "..."}` payload is delivered.

### **2\. Eradicating RAG: The LFM 2.5 Usefulness Node**

Traditional RAG pipelines chunk text, calculate cosine similarities via embedding models, and retrieve the "closest" vectors. However, vector similarity is notoriously bad at determining actual *usefulness* or logical relevance, frequently returning keyword-dense but contextually useless paragraphs.

By utilizing the **LFM 2.5** (SSM-Hybrid) model, we completely bypass RAG. Because SSM-hybrids do not suffer from the quadratic memory scaling of the traditional Transformer Key-Value (KV) cache, they can ingest massive 20,000+ token documents on an 8GB RTX 3070 without overflowing VRAM.

When the Tavily API returns the raw, extracted Markdown of a targeted website, it is passed directly into an LFM 2.5 evaluation prompt:

**System:** You are an expert data triage analyst. **Objective:** Evaluate the provided source document against the `user_query` and the current `research_plan`. **Action:** \> 1\. Does this document contain highly specific facts, statistics, or evidence that directly advances the research plan? 2\. If NO, output `{"is_useful": false, "extracted_facts": []}` and discard the text. 3\. If YES, mathematically extract only the critical data points into dense, highly compressed bullet points. Ignore all narrative fluff.

**Source Document:** \[Raw Tavily Markdown Inserted Here\]

### **3\. The Pure Memory Scratchpad**

If the LFM 2.5 model evaluates the source as `is_useful: true`, the resulting `extracted_facts` array is appended directly into the LangGraph's in-memory `ResearchState` dictionary (the "Scratchpad").

The LFM 2.5 model acts as a highly intelligent, contextual sieve. A 10-page financial report is ingested, evaluated for actual logical utility, compressed into 150 tokens of pure signal, and stored in RAM.

### **4\. Handoff to the Proxy Editor**

Once the Exhaustive Elicitation Loop (from Module E) concludes and all sources have been evaluated by LFM 2.5, the massive, noisy internet has been distilled into a single, dense Python dictionary object containing only verified, useful facts.

At this exact moment, the Python sidecar unloads LFM 2.5 from the GPU VRAM, loads the reasoning model (e.g., **Gemma 4 E4B** or the FastApply Proxy Model), and passes it the entire, highly concentrated Scratchpad to begin the iterative drafting of the final report.

