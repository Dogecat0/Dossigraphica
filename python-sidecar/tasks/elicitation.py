from schemas import ResearchState, ElicitationSchema
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_elicitation(state: ResearchState) -> ResearchState:
    """
    The Exhaustive Elicitation loop.
    Evaluates existing queries and demands additional distinct angles.
    """
    if state.is_exhausted or state.nudge_count >= 3:
        logger.info("Elicitation already exhausted or circuit breaker hit.")
        return state

    logger.info(f"Running Elicitation (Nudge {state.nudge_count + 1})")
    
    current_queries = "\n".join(state.search_queries)
    prompt = (
        f"Original Query: {state.user_query}\n\n"
        f"Current Search Plan:\n{current_queries}\n\n"
        "Identify blind spots. Are you absolutely certain this covers every geopolitical, financial, and historical angle? "
        "Provide at least 3 additional, distinct queries to explore tangential or overlooked angles."
    )
    
    system_prompt = (
        "You are a relentless research director. Review the generated list of search queries "
        "against the original prompt to identify and correct for lazy investigate heuristics."
    )
    
    try:
        elicitation_output = await llm.generate_structured(
            prompt=prompt,
            response_model=ElicitationSchema,
            system_prompt=system_prompt
        )
        
        state.search_queries = list(set(state.search_queries + elicitation_output.additional_items))
        state.is_exhausted = elicitation_output.is_exhausted
        state.nudge_count += 1
        
        logger.info(f"Elicitation added {len(elicitation_output.additional_items)} queries. is_exhausted={state.is_exhausted}")
        return state
        
    except Exception as e:
        logger.error(f"Error in run_elicitation: {e}")
        raise
