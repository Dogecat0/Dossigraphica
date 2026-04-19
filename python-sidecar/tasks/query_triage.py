import json
from schemas import ResearchState, QueryTriageSchema, GeoIntelligenceSchema, INTELLIGENCE_GOALS
from llm import llm
import logging
import os

logger = logging.getLogger(__name__)

# Maximum queries to allow after triage
MAX_TRIAGED_QUERIES = 50

async def run_query_triage(state: ResearchState) -> ResearchState:
    """
    Evaluates the large list of generated search queries and selects the top 50
    to ensure coverage while minimizing redundant Brave API calls.
    """
    if not state.search_queries:
        logger.warning("No search queries to triage.")
        return state

    if len(state.search_queries) <= MAX_TRIAGED_QUERIES:
        logger.info(f"Search queries ({len(state.search_queries)}) within limit. Skipping query triage.")
        return state

    logger.info(f"Triaging {len(state.search_queries)} search queries down to {MAX_TRIAGED_QUERIES}.")

    # 1. Prepare Target Schema and Intelligence Goals
    report_schema = json.dumps(GeoIntelligenceSchema.model_json_schema(), indent=2)
    
    system_prompt = (
        "You are an elite Search Strategy Optimizer. Your goal is to review a large list of "
        "potential search queries and select the most high-signal, non-redundant set to "
        "satisfy a forensic Geo-Intelligence report."
    )

    prompt = (
        f"--- TARGET REPORT SCHEMA ---\n{report_schema}\n\n"
        f"--- INTELLIGENCE GOALS ---\n{INTELLIGENCE_GOALS}\n\n"
        f"--- RAW SEARCH QUERIES ---\n" + "\n".join([f"- {q}" for q in state.search_queries]) + "\n\n"
        f"--- MISSION ---\n"
        f"1. Analyze the raw queries for redundancy and overlap.\n"
        f"2. Group queries that target the same data points (e.g., 'ASML Taiwan revenue' and 'ASML geographic revenue Taiwan').\n"
        f"3. Select the TOP {MAX_TRIAGED_QUERIES} queries that provide the most comprehensive coverage across ALL intelligence modules.\n"
        f"4. Prioritize queries targeting primary sources like SEC filings, transcripts, and official reports.\n"
        f"5. Ensure geographic nodes, supply chain links, and risk categories identified in the goals are specifically targeted."
    )

    try:
        triage_output = await llm.generate_structured(
            prompt=prompt,
            response_model=QueryTriageSchema,
            system_prompt=system_prompt
        )
        
        # Deduplicate and update state
        original_count = len(state.search_queries)
        state.search_queries = list(set(triage_output.top_queries))
        
        # Ensure we don't exceed the hard limit even if the LLM hallucinated more
        if len(state.search_queries) > MAX_TRIAGED_QUERIES:
            state.search_queries = state.search_queries[:MAX_TRIAGED_QUERIES]

        state.scratchpad += f"\n## Query Triage Strategy\n{triage_output.reasoning}\n"
        
        logger.info(f"Query triage reduced {original_count} queries to {len(state.search_queries)}.")
        return state
        
    except Exception as e:
        logger.error(f"Error in run_query_triage: {e}")
        # Fallback: just take the first 50 if LLM fails
        state.search_queries = state.search_queries[:MAX_TRIAGED_QUERIES]
        return state
