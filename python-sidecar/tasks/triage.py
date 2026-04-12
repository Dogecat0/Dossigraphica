import json
from schemas import ResearchState, TriageSchema, GeoIntelligenceSchema, TriageStrategySchema
from llm import llm, LLAMA_CTX_PER_REQUEST, LLAMA_OUTPUT_RESERVATION
import logging
import os
import asyncio

logger = logging.getLogger(__name__)

# Configurable fallback limit and global extraction cap
TRIAGE_FALLBACK_LIMIT = int(os.getenv("TRIAGE_FALLBACK_LIMIT", "5"))
MAX_TOTAL_URLS = 50

async def run_triage(state: ResearchState) -> ResearchState:
    """
    Evaluates Brave search results to rank top URLs via the LLM.
    Executes one inference call PER search query for maximum focus.
    """
    if not state.search_results:
        logger.warning("No search results to triage.")
        return state

    logger.info(f"Triaging {len(state.search_results)} results. Global cap: {MAX_TOTAL_URLS}")
    
    # 1. Prepare Injection Schemas
    # Use f-strings for immediate injection to avoid .format() brace conflicts
    report_schema = json.dumps(GeoIntelligenceSchema.model_json_schema(), indent=2)
    
    # Codify the Strategy into a Data Object
    strategy = TriageStrategySchema(
        authority_hierarchy={
            "tier_1_primary": ["SEC Filings (10-K, 10-Q, 8-K)", "Official Earnings Transcripts", "Investor Presentations"],
            "tier_2_verified": [
                "Official Gov/Regulatory Data (.gov, .int, Customs, Trade, Sanctions)",
                "High-Authority Financial News (WSJ, Bloomberg, Reuters, FT, Digitimes)"
            ]
        },
        max_filing_dates_per_type=2,
        source_penalty_list=["Reddit", "LinkedIn", "Social Media", "General Blogs"],
        diversity_bonus="Maximize domain and source type variety. Do not saturate the 50-URL budget with a single domain.",
        target_date_threshold="Select ONLY the 2 most recent dates for any periodic report, counting back from the date when this query is running."
    )
    strategy_json = json.dumps(strategy.model_dump(), indent=2)

    system_prompt = (
        "You are an expert Geo-Intelligence Triagist. Your goal is to identify primary source "
        "data that contains verifiable geographic information and localized risk disclosures."
    )
    
    # 2. Base prompt template using tags for manual replacement to avoid .format() KeyError on JSON braces
    base_prompt_template = (
        "Analyze these search results for the specific targeted query: <QUERY>\n\n"
        "--- MISSION: SATISFY THIS TARGET REPORT SCHEMA ---\n"
        f"{report_schema}\n\n"
        "--- SELECTION RULES (STRICT COMPLIANCE) ---\n"
        f"{strategy_json}\n\n"
        "--- SEARCH RESULTS ---\n"
        "<SNIPPETS_TEXT>\n\n"
        "Select ONLY the URLs that directly satisfy the query and the Target Report Schema. "
        "Strictly adhere to the Recency and Hierarchy rules. Return them in order of authority."
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
        
        # 1. Calculate tokens based on the *raw* template (with placeholders)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": base_prompt_template}]
        overhead = llm.estimate_tokens(messages)
        target_tokens = LLAMA_CTX_PER_REQUEST - overhead - LLAMA_OUTPUT_RESERVATION
        
        # 2. Summarize snippets to fit
        compressed_snippets = await llm.summarize_to_fit(
            snippets_text, 
            target_tokens, 
            system_prompt="You are a research source triagist. Compress search snippets while keeping URLs and authority signals."
        )

        # 3. Manual Tag Replacement (Robust against JSON braces)
        final_prompt = base_prompt_template.replace("<QUERY>", query).replace("<SNIPPETS_TEXT>", compressed_snippets)
        
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
    unique_urls = []
    seen_urls = set()
    
    # 3. Consolidate and Apply Global Optimization Cap
    for urls, reasoning in triage_results:
        for url in urls:
            if url not in seen_urls:
                unique_urls.append(url)
                seen_urls.add(url)
        combined_reasoning += f"\n### Query Triage\n{reasoning}\n"
    
    if len(unique_urls) > MAX_TOTAL_URLS:
        logger.info(f"Capping unique URLs from {len(unique_urls)} down to {MAX_TOTAL_URLS} for extraction efficiency.")
        unique_urls = unique_urls[:MAX_TOTAL_URLS]
    
    state.scratchpad += combined_reasoning
    state.urls = unique_urls
    
    logger.info(f"Triage complete. Total unique URLs selected for extraction: {len(state.urls)}")
    return state
