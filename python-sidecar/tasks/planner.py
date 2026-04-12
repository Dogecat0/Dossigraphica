import json
from schemas import ResearchState, PlannerSchema, GeoIntelligenceSchema
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_planner(state: ResearchState) -> ResearchState:
    """
    Initiates the Strategy Planner via the reasoning model.
    Injects the final report schema to ensure search queries are forensic and targeted.
    """
    logger.info(f"Running Planner for query: {state.user_query}")
    
    # Generate the JSON schema for the final report to inject into the prompt
    report_schema = json.dumps(GeoIntelligenceSchema.model_json_schema(), indent=2)
    
    prompt = (
        f"Act as a Senior Geopolitical Risk & Corporate Intelligence Analyst. "
        f"Your client requires a forensic Geo-Intelligence Brief for: {state.user_query}\n\n"
        f"--- TARGET REPORT SCHEMA ---\n"
        f"The final output MUST populate the following data structure:\n"
        f"{report_schema}\n\n"
        f"--- MISSION ---\n"
        f"Decompose the request into a forensic research plan. You must generate precise "
        f"search queries that target the specific fields, enums, and nested objects defined in the schema above. "
        f"Focus on SEC filings (10-K, 10-Q, 8-K), earnings transcripts, and official press releases as primary sources. "
        f"Ensure no geographic nodes, revenue segments, or risk categories are missed."
    )
    
    system_prompt = (
        "You are an elite Geo-Intelligence Research Strategist. Your task is to decompose "
        "complex corporate queries into a structured research plan. You generate search "
        "queries specifically designed to extract data points that satisfy a strict forensic JSON schema."
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
