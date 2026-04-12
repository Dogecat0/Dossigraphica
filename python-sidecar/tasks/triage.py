from schemas import ResearchState, TriageSchema
from llm import llm, LLAMA_CTX_PER_REQUEST, LLAMA_OUTPUT_RESERVATION
import logging
import os
import asyncio

logger = logging.getLogger(__name__)

# Configurable fallback limit
TRIAGE_FALLBACK_LIMIT = int(os.getenv("TRIAGE_FALLBACK_LIMIT", "5"))

async def run_triage(state: ResearchState) -> ResearchState:
    """
    Evaluates SearXNG snippets to rank top URLs via the LLM.
    Executes one inference call PER search query for maximum focus.
    """
    if not state.search_results:
        logger.warning("No search results to triage.")
        return state

    logger.info(f"Triaging {len(state.search_results)} search results across queries.")
    
    system_prompt = (
        "You are an expert Geo-Intelligence Triagist. Your goal is to identify primary source "
        "data (SEC filings, official press releases) that contains verifiable geographic "
        "information and localized risk disclosures."
    )
    
    # Base prompt template for per-query triage
    base_prompt_template = (
        "Analyze these search results for the specific targeted query: {query}\n\n"
        "Search results:\n{snippets_text}\n\n"
        "Identify all highly authoritative sources following this hierarchy:\n"
        "1. Tier 1 (Highest): SEC Filings (10-K, 10-Q, Exhibit 21), Official Earnings Call Transcripts, Investor Presentations.\n"
        "2. Tier 2 (High): Bloomberg, WSJ, Reuters, FT.\n"
        "3. Tier 3 (Medium): Established trade publications.\n\n"
        "Select only the sources that directly satisfy the query and contain verifiable geographic data. "
        "Return the URLs in order of authority and relevance."
    )

    # Group snippets by query
    query_groups = {}
    for res in state.search_results:
        q = res.get("query") or state.user_query
        if q not in query_groups:
            query_groups[q] = []
        query_groups[q].append(res)

    all_top_urls = []
    
    async def triage_query(query, results):
        snippets_text = ""
        for i, res in enumerate(results):
            snippets_text += f"[{i}] URL: {res['url']}\nTitle: {res['title']}\nSnippet: {res['content']}\n\n"
        
        # Calculate available token space
        test_prompt = base_prompt_template.format(query=query, snippets_text="")
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": test_prompt}]
        overhead = llm.estimate_tokens(messages)
        target_tokens = LLAMA_CTX_PER_REQUEST - overhead - LLAMA_OUTPUT_RESERVATION
        
        # Summarize to fit if necessary
        compressed_snippets = await llm.summarize_to_fit(
            snippets_text, 
            target_tokens, 
            system_prompt="You are a research source triagist. Compress search snippets while keeping URLs and authority signals."
        )

        final_prompt = base_prompt_template.format(query=query, snippets_text=compressed_snippets)
        
        try:
            triage_output = await llm.generate_structured(
                prompt=final_prompt,
                response_model=TriageSchema,
                system_prompt=system_prompt
            )
            logger.info(f"Triage for query '{query[:30]}...' selected {len(triage_output.top_urls)} URLs.")
            return triage_output.top_urls, triage_output.reasoning
        except Exception as e:
            logger.error(f"Error in triage for query '{query}': {e}")
            return [r["url"] for r in results[:3]], f"Fallback due to error: {e}"

    # Execute triage for each query in parallel
    triage_tasks = [triage_query(q, res) for q, res in query_groups.items()]
    triage_results = await asyncio.gather(*triage_tasks)
    
    combined_reasoning = ""
    unique_urls = set()
    for urls, reasoning in triage_results:
        for url in urls:
            unique_urls.add(url)
        combined_reasoning += f"\n### Query Triage\n{reasoning}\n"
    
    state.scratchpad += combined_reasoning
    state.urls = list(unique_urls)
    
    logger.info(f"Triage complete. Total unique URLs selected: {len(state.urls)}")
    return state
