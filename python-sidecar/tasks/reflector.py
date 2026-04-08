from schemas import ResearchState, ReflectorSchema
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_reflector(state: ResearchState) -> ResearchState:
    """
    Evaluates the current facts against the research goals.
    Identifies gaps and generates new search queries for the next loop.
    """
    if not state.extracted_facts:
        logger.warning("No facts extracted yet. Reflector will force another search loop.")
        state.is_complete = False
        return state

    logger.info("Running Reflector.")
    
    facts_text = "\n".join([f"- {fact}" for fact in state.extracted_facts])
    
    prompt = (
        f"Research Query: {state.user_query}\n\n"
        f"Extracted Facts:\n{facts_text}\n\n"
        "Evaluate the progress. Does this answer the original query comprehensively? "
        "Identify specific gaps in the data (e.g., missing revenue breakdowns, unclear supply chain links, outdated risk scores). "
        "If gaps exist, provide new targeted search queries to fill them. "
        "If the query is fully answered, set is_complete to True."
    )
    
    system_prompt = (
        "You are an adversarial research auditor. Your job is to find flaws in the current gathered "
        "intelligence and demand more evidence unless the query is definitively answered."
    )
    
    try:
        reflector_output = await llm.generate_structured(
            prompt=prompt,
            response_model=ReflectorSchema,
            system_prompt=system_prompt
        )
        
        state.scratchpad += f"\n## Reflection & Gap Analysis\n{reflector_output.reasoning}\n"
        
        if not reflector_output.is_complete:
            state.search_queries = reflector_output.new_queries
            logger.info(f"Reflection: Not complete. Added {len(reflector_output.new_queries)} new queries.")
        else:
            logger.info("Reflection: Research goal achieved.")
            
        state.is_complete = reflector_output.is_complete
        return state
        
    except Exception as e:
        logger.error(f"Error in run_reflector: {e}")
        # Default to not complete to avoid early stopping
        state.is_complete = False
        return state
