from schemas import ResearchState, PlannerSchema, INTELLIGENCE_GOALS
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_planner(state: ResearchState) -> ResearchState:
    """
    Initiates the Strategy Planner via the reasoning model.
    Updates the state with reasoning and initial search queries.
    """
    logger.info(f"Running Planner for query: {state.user_query}")
    
    prompt = (
        f"Act as a Senior Geopolitical Risk & Corporate Intelligence Analyst. "
        f"Your client requires a highly specific, geographically focused Geo-Intelligence Brief for: {state.user_query}\n\n"
        f"{INTELLIGENCE_GOALS}\n\n"
        f"Mission: Decompose the request into a forensic research plan that satisfies ALL these modules. "
        f"Focus on SEC filings (10-K, 10-Q, 8-K), earnings transcripts, and official press releases as primary sources. "
        f"Generate precise search queries for each module to ensure no geographic nodes or revenue segments are missed."
    )
    
    system_prompt = (
        "You are an elite Geo-Intelligence Research Strategist. Your task is to decompose "
        "complex corporate queries into a structured research plan that maps physical assets, "
        "regional revenue, supply chain nodes, and jurisdictional risks."
    )
    
    try:
        planner_output = await llm.generate_structured(
            prompt=prompt,
            response_model=PlannerSchema,
            system_prompt=system_prompt
        )
        
        state.scratchpad += f"\n## Research Strategy\n{planner_output.reasoning}\n"
        state.search_queries = list(set(state.search_queries + planner_output.search_queries))
        
        logger.info(f"Planner generated {len(planner_output.search_queries)} queries.")
        return state
        
    except Exception as e:
        logger.error(f"Error in run_planner: {e}")
        raise
