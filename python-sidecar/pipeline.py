from schemas import ResearchState
from tasks.planner import run_planner
from tasks.elicitation import run_elicitation
from tasks.search import run_search
from tasks.triage import run_triage
from tasks.extractor import run_extractor
from tasks.preprocessor import run_preprocessor
from tasks.drafter import run_drafter
from utils.log_replay import reconstruct_state_from_logs
import logging
import json
import asyncio
import os

logger = logging.getLogger(__name__)

# Configurable loop limits
ELICITATION_MAX_NUDGES = int(os.getenv("ELICITATION_MAX_NUDGES", "20"))

async def research_pipeline(query: str):
    """
    The Pure Python Orchestration Engine.
    Single-pass pipeline: Plan → Elicitate → Search → Triage → Extract → Preprocess → Draft → Deliver.
    The Elicitation loop guarantees exhaustive query coverage upfront,
    eliminating the need for a costly reflector feedback loop.
    """
    # Initialize State from logs or scratch
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
    state = reconstruct_state_from_logs(query, log_dir)
    
    if state.pipeline_step != "init":
        logger.info(f"Resuming pipeline for: {query} from step: {state.pipeline_step}")
    else:
        logger.info(f"Starting pipeline for: {query}")

    try:
        # 1. Strategy & Planning
        if state.pipeline_step == "init":
            yield json.dumps({"status": "planning", "message": "Developing research strategy...", "progress": 5})
            state = await run_planner(state)
            state.pipeline_step = "elicitation"
        
        # 2. Exhaustive Elicitation (Is That All? Protocol)
        if state.pipeline_step == "elicitation":
            while not state.is_exhausted and state.nudge_count < ELICITATION_MAX_NUDGES:
                yield json.dumps({
                    "status": "elicitation", 
                    "message": f"Refining search queries (Iteration {state.nudge_count + 1}/{ELICITATION_MAX_NUDGES})...",
                    "queries": state.search_queries,
                    "progress": 10 + (state.nudge_count * 2)
                })
                state = await run_elicitation(state)
            state.pipeline_step = "searching"

        # 3. Search (Tavily Discovery)
        if state.pipeline_step == "searching":
            yield json.dumps({
                "status": "searching", 
                "message": f"Executing {len(state.search_queries)} search queries...",
                "queries": state.search_queries,
                "progress": 50
            })
            state = await run_search(state)
            state.pipeline_step = "triage"
        
        # 4. Triage (LLM Source Ranking)
        if state.pipeline_step == "triage":
            yield json.dumps({"status": "triage", "message": "Ranking most authoritative sources...", "progress": 58})
            state = await run_triage(state)
            state.pipeline_step = "extracting"
        
        # 5. Managed Extraction (Tavily)
        if state.pipeline_step == "extracting":
            yield json.dumps({"status": "extracting", "message": f"Extracting content from {len(state.urls)} URLs...", "progress": 65})
            state = await run_extractor(state)
            state.pipeline_step = "preprocessing"
        
        # 6. Semantic Sieve & Chunking (Preprocessor - Early Squeeze)
        if state.pipeline_step == "preprocessing":
            yield json.dumps({"status": "preprocessing", "message": "Chunking and extracting facts from large documents...", "progress": 72})
            state = await run_preprocessor(state)
            state.pipeline_step = "drafting"
        
        # 7. Final Handoff (Parallel Drafting)
        if state.pipeline_step == "drafting":
            yield json.dumps({"status": "drafting", "message": "Synthesizing final intelligence report...", "progress": 85})
            state = await run_drafter(state)
            state.pipeline_step = "completed"
        
        # 8. Delivery
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
