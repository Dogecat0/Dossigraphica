import httpx
import os
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")

async def run_search(state: ResearchState) -> ResearchState:
    """
    Calls the local SearXNG Docker container via HTTP.
    Returns URLs and snippets for each search query.
    """
    if not state.search_queries:
        logger.warning("No search queries provided to run_search.")
        return state

    logger.info(f"Running SearXNG search for {len(state.search_queries)} queries.")
    
    all_results = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in state.search_queries:
            logger.info(f"Searching for: {query}")
            try:
                response = await client.get(
                    f"{SEARXNG_URL}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "engines": "google,bing,duckduckgo",
                        "language": "en-US"
                    }
                )
                response.raise_for_status()
                results = response.json()
                
                # Each result in SearXNG results is usually { 'url': ..., 'content': ..., 'title': ... }
                # We want to extract unique URLs and maybe snippets for triage
                found_results = results.get("results", [])
                logger.info(f"Found {len(found_results)} results for query: {query}")
                
                # Append found results to state.search_results for Triage
                for res in found_results:
                    url = res.get("url")
                    if url and not any(r["url"] == url for r in all_results):
                        all_results.append({
                            "url": url,
                            "content": res.get("content", ""),
                            "title": res.get("title", ""),
                            "query": query
                        })
                
            except Exception as e:
                logger.error(f"Error searching for query '{query}': {e}")
                continue
                
    state.search_results = all_results
    state.urls = [r["url"] for r in all_results]
    logger.info(f"SearXNG finished. Total unique search results in state: {len(state.search_results)}")
    return state
