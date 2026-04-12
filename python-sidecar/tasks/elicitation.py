import json
from schemas import ResearchState, ElicitationSchema, GeoIntelligenceSchema
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_elicitation(state: ResearchState) -> ResearchState:
    """
    The Exhaustive Elicitation loop.
    Evaluates existing queries against the target schema and demands additional distinct angles.
    """
    if state.is_exhausted:
        logger.info("Elicitation already exhausted.")
        return state

    logger.info(f"Running Elicitation (Nudge {state.nudge_count + 1})")
    
    # 1. Prepare Target Schema
    report_schema = json.dumps(GeoIntelligenceSchema.model_json_schema(), indent=2)
    
    current_queries = "\n".join(state.search_queries)
    
    # 2. Use a robust template with tags to avoid brace conflicts
    base_prompt_template = (
        "Original Query: <USER_QUERY>\n\n"
        "--- TARGET REPORT SCHEMA ---\n"
        f"{report_schema}\n\n"
        "--- CURRENT SEARCH PLAN ---\n"
        "<CURRENT_QUERIES>\n\n"
        "--- MISSION ---\n"
        "Identify blind spots in the Geo-Intelligence narrative. Review the Target Report Schema "
        "and determine which specific forensic fields, geographic nodes, or risk categories are missing "
        "from the current search plan. Generate additional precise queries to fill these gaps."
    )
    
    prompt = base_prompt_template.replace("<USER_QUERY>", state.user_query).replace("<CURRENT_QUERIES>", current_queries)
    
    system_prompt = (
        "You are a relentless Geo-Intelligence Director. Review the search plan "
        "to ensure absolute forensic coverage of physical infrastructure and geopolitical exposure "
        "as defined by the strict forensic schema."
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
