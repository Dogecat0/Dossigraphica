import httpx
import os
import asyncio
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

async def run_search(state: ResearchState) -> ResearchState:
    """
    Calls the Tavily Search API in parallel.
    Returns URLs and snippets for each search query.
    """
    if not state.search_queries:
        logger.warning("No search queries provided to run_search.")
        return state

    if not TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY environment variable is not set. Cannot perform search.")
        return state

    logger.info(f"Running Tavily search for {len(state.search_queries)} queries in parallel.")
    
    unique_results = {} # Use dict to deduplicate by URL easily
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def fetch_query(query: str):
            logger.info(f"Searching for: {query}")
            try:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {TAVILY_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 5,
                        "include_answer": False,
                        "include_raw_content": False
                    }
                )
                response.raise_for_status()
                data = response.json()
                found = data.get("results", [])
                logger.info(f"Query '{query}' returned {len(found)} results.")
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
                    unique_results[url] = {
                        "url": url,
                        "content": res.get("content", ""),
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
        logger.info(f"Tavily Search logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log SearchData: {e}")

    logger.info(f"Tavily Search finished. Total unique search results in state: {len(state.search_results)}")
    return state
