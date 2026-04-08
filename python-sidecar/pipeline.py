from schemas import ResearchState
from tasks.planner import run_planner
from tasks.elicitation import run_elicitation
from tasks.search import run_search
from tasks.triage import run_triage
from tasks.extractor import run_extractor
from tasks.preprocessor import run_preprocessor
from tasks.reflector import run_reflector
from tasks.drafter import run_drafter
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

async def research_pipeline(query: str):
    """
    The Pure Python Orchestration Engine (The Ralph Loop).
    Runs a strict while loop, awaiting task functions and yielding JSON updates for SSE.
    """
    # Initialize State
    state = ResearchState(user_query=query)
    logger.info(f"Starting pipeline for: {query}")

    try:
        # 1. Strategy & Planning
        yield json.dumps({"status": "planning", "message": "Developing research strategy..."})
        state = await run_planner(state)
        
        # 2. Exhaustive Elicitation (Is That All? Protocol)
        while not state.is_exhausted and state.nudge_count < 3:
            yield json.dumps({
                "status": "elicitation", 
                "message": f"Refining search queries (Iteration {state.nudge_count + 1})...",
                "queries": state.search_queries
            })
            state = await run_elicitation(state)

        # 3. Main Research Loop (Aggregation -> Triage -> Extraction -> Squeezing -> Reflection)
        loop_count = 0
        max_loops = 5 # Safety circuit breaker

        while not state.is_complete and loop_count < max_loops:
            loop_count += 1
            yield json.dumps({
                "status": "searching", 
                "message": f"Executing search queries (Loop {loop_count})...",
                "queries": state.search_queries
            })
            
            # Discovery (SearXNG)
            state = await run_search(state)
            
            # Triage (Ranking)
            yield json.dumps({"status": "triage", "message": "Ranking most authoritative sources..."})
            state = await run_triage(state)
            
            # Managed Extraction (Tavily)
            yield json.dumps({"status": "extracting", "message": f"Extracting content from {len(state.urls)} URLs..."})
            state = await run_extractor(state)
            
            # Semantic Sieve & Chunking (Preprocessor - Early Squeeze)
            yield json.dumps({"status": "preprocessing", "message": "Chunking and extracting facts from large documents..."})
            state = await run_preprocessor(state)
            
            # Reflection & Critique (Adversarial Judge)
            yield json.dumps({"status": "reflecting", "message": "Evaluating research progress and identifying gaps..."})
            state = await run_reflector(state)
            
            if state.is_complete:
                logger.info("Research goals met. Proceeding to drafting.")
                break
            else:
                logger.info(f"Gaps identified. Starting search loop {loop_count + 1}.")

        # 4. Final Handoff (Iterative Drafting)
        yield json.dumps({"status": "drafting", "message": "Synthesizing final intelligence report..."})
        state = await run_drafter(state)
        
        # 5. Delivery
        yield json.dumps({
            "status": "completed", 
            "message": "Research complete.",
            "report": state.final_report_md,
            "data": state.final_report_json
        })
        
        logger.info(f"Pipeline finished for: {query}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        yield json.dumps({"status": "error", "message": str(e)})
