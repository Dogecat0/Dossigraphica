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
        "Identify the top 5 most authoritative, relevant, and information-dense URLs "
        "that are likely to contain primary source data (SEC filings, official press releases, deep industry analysis)."
    )
    
    system_prompt = (
        "You are an expert information triagist. Your goal is to separate high-signal authoritative "
        "sources from SEO spam and redundant news aggregators."
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
