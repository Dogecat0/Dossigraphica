import httpx
import os
import asyncio
from schemas import ResearchState
from utils.io_cache import DiskCache
from utils.rate_limiter import MinuteRateLimiter
from checkpoint import save_checkpoint
import logging

logger = logging.getLogger(__name__)

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "brave").lower()
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY")
TINYFISH_SEARCH_RPM = int(os.getenv("TINYFISH_SEARCH_RPM", "30"))

_search_cache = DiskCache("search_cache.json")
_tinyfish_search_cache = DiskCache("tinyfish_search_cache.json")
_tinyfish_search_limiter = MinuteRateLimiter(TINYFISH_SEARCH_RPM)

# Max TinyFish query-param length (conservative; actual server limit is ~8 KB via GET)
MAX_TINYFISH_QUERY_LENGTH = 6000


def _build_site_exclusions(query: str, blocked: dict[str, int]) -> str:
    """
    Append `-site:domain.com` exclusions to a TinyFish search query,
    sorted by block frequency (most-blocked first). Truncates at
    MAX_TINYFISH_QUERY_LENGTH so the total query stays under the
    practical GET-request limit.

    Args:
        query: The original search query string.
        blocked: dict of domain → block-count.

    Returns:
        The query string with as many -site: exclusions as fit within
        MAX_TINYFISH_QUERY_LENGTH, ordered by descending count.
    """
    if not blocked:
        return query

    sorted_domains = sorted(blocked.items(), key=lambda x: -x[1])

    exclusion_parts: list[str] = []
    for domain, count in sorted_domains:
        term = f"-site:{domain}"
        candidate_length = len(query) + sum(len(p) + 1 for p in exclusion_parts) + 1 + len(term)
        if candidate_length <= MAX_TINYFISH_QUERY_LENGTH:
            exclusion_parts.append(term)

    fitted = len(exclusion_parts)
    total = len(sorted_domains)
    if fitted < total:
        logger.debug(
            f"Query length limit reached: fitted {fitted}/{total} -site: exclusions "
            f"(dropped {sorted_domains[fitted][0]} with count={sorted_domains[fitted][1]}, "
            f"and {total - fitted - 1} less-frequent domains)"
        )

    if exclusion_parts:
        return query + " " + " ".join(exclusion_parts)
    return query


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
            enriched_query = _build_site_exclusions(query, state.blocked_domains)
            cache_key = enriched_query.strip().lower()
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
                        "query": enriched_query
                    }

                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    found = data.get("results", [])
                    logger.debug(f"Query '{query}' returned {len(found)} results from TinyFish.")
                    await _tinyfish_search_cache.set(cache_key, found)
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
    
    await save_checkpoint("SearchData", {
        "search_results": state.search_results,
        "urls": state.urls
    })

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
                    await _search_cache.set(cache_key, found)
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
    
    await save_checkpoint("SearchData", {
        "search_results": state.search_results,
        "urls": state.urls
    })

    logger.debug(f"Brave Search finished. Total unique search results in state: {len(state.search_results)}")
    return state

