from schemas import ResearchState, TriageSchema
from llm import llm
import logging

logger = logging.getLogger(__name__)

async def run_triage(state: ResearchState) -> ResearchState:
    """
    Evaluates SearXNG snippets to rank top URLs via the LLM.
    Limits the number of URLs to pass to the extractor.
    """
    if not state.search_results:
        logger.warning("No search results to triage.")
        return state

    logger.info(f"Triaging {len(state.search_results)} search results.")
    
    # Format the snippets for the LLM
    snippets_text = ""
    for i, res in enumerate(state.search_results[:20]): # Limit to first 20 for triage context
        snippets_text += f"[{i}] URL: {res['url']}\nTitle: {res['title']}\nSnippet: {res['content']}\n\n"
        
    prompt = (
        f"Analyze these search results for the query: {state.user_query}\n\n"
        f"Search results:\n{snippets_text}\n"
        "Identify the top 5 most authoritative sources following this hierarchy:\n"
        "1. Tier 1 (Highest): SEC Filings (10-K, 10-Q, Exhibit 21), Official Earnings Call Transcripts, Investor Presentations.\n"
        "2. Tier 2 (High): Bloomberg, WSJ, Reuters, FT.\n"
        "3. Tier 3 (Medium): Established trade publications.\n\n"
        "Look specifically for physical locations, regional revenue breakdowns, and supply chain nodes."
    )
    
    system_prompt = (
        "You are an expert Geo-Intelligence Triagist. Your goal is to identify primary source "
        "data (SEC filings, official press releases) that contains verifiable geographic "
        "information and localized risk disclosures."
    )
    
    try:
        triage_output = await llm.generate_structured(
            prompt=prompt,
            response_model=TriageSchema,
            system_prompt=system_prompt
        )
        
        state.scratchpad += f"\n## Source Triage Reasoning\n{triage_output.reasoning}\n"
        # Filter to only the top URLs selected by LLM
        state.urls = triage_output.top_urls
        
        logger.info(f"Triage selected {len(state.urls)} top URLs.")
        return state
        
    except Exception as e:
        logger.error(f"Error in run_triage: {e}")
        # Fallback: just use top 5 by SearXNG ranking
        state.urls = [r["url"] for r in state.search_results[:5]]
        logger.warning("Falling back to top 5 SearXNG results due to triage failure.")
        return state
