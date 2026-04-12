import httpx
import os
import asyncio
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")

async def run_search(state: ResearchState) -> ResearchState:
    """
    Calls the Brave Search API in parallel.
    Returns URLs and snippets for each search query.
    """
    if not state.search_queries:
        logger.warning("No search queries provided to run_search.")
        return state

    if not BRAVE_SEARCH_API_KEY:
        logger.error("BRAVE_SEARCH_API_KEY environment variable is not set. Cannot perform search.")
        return state

    logger.info(f"Running Brave search for {len(state.search_queries)} queries in parallel.")
    
    unique_results = {} # Use dict to deduplicate by URL easily
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def fetch_query(query: str):
            logger.info(f"Searching for: {query}")
            try:
                # Brave Search API: Web Search Endpoint
                url = "https://api.search.brave.com/res/v1/web/search"
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_SEARCH_API_KEY
                }
                params = {
                    "q": query,
                    "count": 10 # Request up to 10 results for better coverage
                }
                
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Brave results are nested under web -> results
                found = data.get("web", {}).get("results", [])
                logger.info(f"Query '{query}' returned {len(found)} results from Brave.")
                return found, query
            except Exception as e:
                logger.error(f"Error searching for query '{query}': {e}")
                return [], query

        # Execute all queries concurrently
        search_tasks = [fetch_query(q) for q in state.search_queries]
        all_query_results = await asyncio.gather(*search_tasks)

        for results, query in all_query_results:
            for res in results:
                url = res.get("url")
                if url and url not in unique_results:
                    # Brave uses 'description' for the snippet
                    unique_results[url] = {
                        "url": url,
                        "content": res.get("description", ""),
                        "title": res.get("title", ""),
                        "query": query
                    }
                
    state.search_results = list(unique_results.values())
    state.urls = list(unique_results.keys())
    
    # Store for replay
    from llm import llm
    import json
    try:
        async with llm.counter_lock:
            llm.inference_counter += 1
            current_index = llm.inference_counter
            
        filepath = os.path.join(llm.log_dir, f"{current_index:04d}_SearchData_output.json")
        with open(filepath, "w") as f:
            json.dump({
                "search_results": state.search_results,
                "urls": state.urls
            }, f, indent=2)
        logger.info(f"Brave Search logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log SearchData: {e}")

    logger.info(f"Brave Search finished. Total unique search results in state: {len(state.search_results)}")
    return state
