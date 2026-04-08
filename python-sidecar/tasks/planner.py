from schemas import ResearchState, PlannerSchema
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
        f"Analyze the following research query and generate a comprehensive research plan.\n"
        f"Query: {state.user_query}\n\n"
        f"Identify the key technical, geopolitical, and economic facets that must be investigated."
    )
    
    system_prompt = (
        "You are an elite research strategist. Your task is to decompose complex queries "
        "into a structured research plan and actionable search strings."
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
