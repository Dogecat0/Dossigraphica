import httpx
import os
import asyncio
import json
from schemas import ResearchState
from utils.io_cache import DiskCache
from utils.rate_limiter import MinuteRateLimiter
import logging

logger = logging.getLogger(__name__)

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "brave").lower()
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY")
TINYFISH_SEARCH_RPM = int(os.getenv("TINYFISH_SEARCH_RPM", "30"))

_search_cache = DiskCache("search_cache.json")
_tinyfish_search_cache = DiskCache("tinyfish_search_cache.json")
_tinyfish_search_limiter = MinuteRateLimiter(TINYFISH_SEARCH_RPM)


async def _run_tinyfish_search(state: ResearchState) -> ResearchState:
    """
    Calls the TinyFish Search API in parallel.
    Returns URLs and snippets for each search query.
    """
    if not state.search_queries:
        logger.warning("No search queries provided to _run_tinyfish_search.")
        return state

    if not TINYFISH_API_KEY:
        logger.error("TINYFISH_API_KEY environment variable is not set. Cannot perform TinyFish search.")
        return state

    logger.debug(f"Running TinyFish search for {len(state.search_queries)} queries in parallel.")
    
    unique_results = {}

    # Semaphore caps concurrent in-flight connections; rate limiter enforces the 30 RPM window.
    semaphore = asyncio.Semaphore(10)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def fetch_query(query: str, index: int):
            cache_key = query.strip().lower()
            cached = _tinyfish_search_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"TinyFish Search cache HIT for query: '{query}' ({len(cached)} results)")
                return cached, query

            async with semaphore:
                await _tinyfish_search_limiter.acquire()
                logger.debug(f"TinyFish Searching for: {query}")
                try:
                    url = "https://api.search.tinyfish.ai"
                    headers = {
                        "Accept": "application/json",
                        "X-API-Key": TINYFISH_API_KEY
                    }
                    params = {
                        "query": query
                    }

                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    found = data.get("results", [])
                    logger.debug(f"Query '{query}' returned {len(found)} results from TinyFish.")
                    _tinyfish_search_cache.set(cache_key, found)
                    return found, query
                except Exception as e:
                    logger.error(f"Error searching TinyFish for query '{query}': {e}")
                    return [], query

        # Execute all queries concurrently with staggering
        search_tasks = [fetch_query(q, i) for i, q in enumerate(state.search_queries)]
        all_query_results = await asyncio.gather(*search_tasks)

        for results, query in all_query_results:
            for res in results:
                url = res.get("url")
                if url and url not in unique_results:
                    unique_results[url] = {
                        "url": url,
                        "content": res.get("snippet", ""),
                        "title": res.get("title", ""),
                        "query": query
                    }
                
    state.search_results = list(unique_results.values())
    state.urls = list(unique_results.keys())
    
    # Store for replay
    from llm import llm
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
        logger.debug(f"TinyFish Search logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log SearchData: {e}")

    logger.debug(f"TinyFish Search finished. Total unique search results in state: {len(state.search_results)}")
    return state


async def run_search(state: ResearchState) -> ResearchState:
    """
    Dispatcher to run search using the configured provider.
    """
    if SEARCH_PROVIDER == "tinyfish":
        return await _run_tinyfish_search(state)

    # Fallback to default Brave Search
    if not state.search_queries:
        logger.warning("No search queries provided to run_search.")
        return state

    if not BRAVE_SEARCH_API_KEY:
        logger.error("BRAVE_SEARCH_API_KEY environment variable is not set. Cannot perform search.")
        return state

    logger.debug(f"Running Brave search for {len(state.search_queries)} queries in parallel.")
    
    unique_results = {} # Use dict to deduplicate by URL easily
    
    # Semaphore to prevent 429 errors while respecting limits
    # We allow higher concurrency here since Brave rate limit is higher (50 QPS)
    semaphore = asyncio.Semaphore(50)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def fetch_query(query: str, index: int):
            cache_key = query.strip().lower()
            cached = _search_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Search cache HIT for query: '{query}' ({len(cached)} results)")
                return cached, query

            # Stagger requests to stay under 50 QPS (1 request every ~0.02s)
            # We add a slight margin by using 0.025s
            await asyncio.sleep(index * 0.025)
            async with semaphore:
                logger.debug(f"Searching for: {query}")
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
                        "count": 20 # Request up to 20 results for better coverage
                    }

                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    # Brave results are nested under web -> results
                    found = data.get("web", {}).get("results", [])
                    logger.debug(f"Query '{query}' returned {len(found)} results from Brave.")
                    _search_cache.set(cache_key, found)
                    return found, query
                except Exception as e:
                    logger.error(f"Error searching for query '{query}': {e}")
                    return [], query

        # Execute all queries concurrently with staggering
        search_tasks = [fetch_query(q, i) for i, q in enumerate(state.search_queries)]
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
        logger.debug(f"Brave Search logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log SearchData: {e}")

    logger.debug(f"Brave Search finished. Total unique search results in state: {len(state.search_results)}")
    return state

