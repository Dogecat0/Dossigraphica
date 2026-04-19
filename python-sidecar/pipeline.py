from schemas import ResearchState
from tasks.planner import run_planner
from tasks.search import run_search
from tasks.source_triage import run_source_triage
from tasks.extractor import run_extractor
from tasks.preprocessor import run_preprocessor
from tasks.drafter import run_drafter
from utils.log_replay import reconstruct_state_from_logs
import logging
import json
import asyncio
import os

logger = logging.getLogger(__name__)

async def research_pipeline(query: str):
    """
    The Pure Python Orchestration Engine.
    Single-pass pipeline: Plan → Search → Source Triage → Extract → Preprocess → Draft → Deliver.
    The planner deterministically generates queries from schema introspection,
    eliminating the need for elicitation and query triage stages.
    """
    # Initialize State from logs or scratch
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
    state = reconstruct_state_from_logs(query, log_dir)
    
    if state.pipeline_step != "init":
        logger.info(f"Resuming pipeline for: {query} from step: {state.pipeline_step}")
    else:
        logger.info(f"Starting pipeline for: {query}")

    try:
        # 1. Deterministic Planning (Schema Introspection)
        if state.pipeline_step == "init":
            yield json.dumps({"status": "planning", "message": "Generating research queries from schema...", "progress": 5})
            state = await run_planner(state)
            state.pipeline_step = "searching"

        # 2. Search (Brave Discovery)
        if state.pipeline_step == "searching":
            yield json.dumps({
                "status": "searching", 
                "message": f"Executing {len(state.search_queries)} search queries...",
                "queries": state.search_queries,
                "progress": 50
            })
            state = await run_search(state)
            state.pipeline_step = "source_triage"
        
        # 3. LLM Source Triage (SEO Filtering)
        if state.pipeline_step == "source_triage":
            yield json.dumps({"status": "source_triage", "message": f"Evaluating {len(state.search_results)} search snippets to discard SEO spam...", "progress": 55})
            state = await run_source_triage(state)
            state.pipeline_step = "extracting"

        # 4. Managed Extraction (Jina Reader)
        if state.pipeline_step == "extracting":
            yield json.dumps({"status": "extracting", "message": f"Extracting content from {len(state.urls)} URLs...", "progress": 65})
            state = await run_extractor(state)
            state.pipeline_step = "preprocessing"
        
        # 5. Semantic Sieve & Chunking (Preprocessor - Early Squeeze)
        if state.pipeline_step == "preprocessing":
            yield json.dumps({"status": "preprocessing", "message": "Chunking and extracting facts from large documents...", "progress": 72})
            state = await run_preprocessor(state)
            state.pipeline_step = "drafting"
        
        # 6. Final Handoff (Parallel Drafting)
        if state.pipeline_step == "drafting":
            yield json.dumps({"status": "drafting", "message": "Synthesizing final intelligence report...", "progress": 85})
            state = await run_drafter(state)
            state.pipeline_step = "completed"
        
        # 7. Delivery
        yield json.dumps({
            "status": "completed", 
            "message": "Research complete.",
            "report": state.final_report_md,
            "data": state.final_report_json,
            "progress": 100
        })
        
        logger.info(f"Pipeline finished for: {query}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        yield json.dumps({"status": "error", "message": str(e)})
