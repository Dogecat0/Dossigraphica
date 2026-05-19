import httpx
import os
import json
import asyncio
import time
from typing import AsyncGenerator, Union
from urllib.parse import urlparse
from schemas import ResearchState
from utils.io_cache import DiskCache
from utils.rate_limiter import MinuteRateLimiter
import logging

logger = logging.getLogger(__name__)

_jina_cache = DiskCache("jina_cache.json")
_tinyfish_cache = DiskCache("tinyfish_cache.json")

FETCH_PROVIDER = os.getenv("FETCH_PROVIDER", "jina").lower()
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY")
TINYFISH_FETCH_BATCH_SIZE = 10

# Rate limits (free tier defaults; override via env vars when upgrading plans)
# Search: 30 req/min  →  enforced in search.py via MinuteRateLimiter
# Fetch:  150 url/min →  acquire(len(batch)) before each POST
TINYFISH_FETCH_URL_PM = int(os.getenv("TINYFISH_FETCH_URL_PM", "150"))
_tinyfish_fetch_limiter = MinuteRateLimiter(TINYFISH_FETCH_URL_PM)

# Fallback fetch provider: used when the primary provider fails for a URL.
# Valid values: 'jina', 'tinyfish', 'none'. Must differ from FETCH_PROVIDER.
_raw_fallback = os.getenv("FETCH_FALLBACK_PROVIDER", "none").lower()
if _raw_fallback != "none" and _raw_fallback == FETCH_PROVIDER:
    logger.warning(
        f"FETCH_FALLBACK_PROVIDER='{_raw_fallback}' is the same as FETCH_PROVIDER. "
        "Fallback disabled (set to 'none')."
    )
    FETCH_FALLBACK_PROVIDER = "none"
else:
    FETCH_FALLBACK_PROVIDER = _raw_fallback

# Persistent blocklist: stored at sidecar root (outside logs/ so it survives log wipes)
BLOCKLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blocked_domains.json")


def _persist_blocklist(state: ResearchState) -> None:
    """Write the current blocked_domains set to disk for cross-run persistence."""
    try:
        with open(BLOCKLIST_PATH, "w") as f:
            json.dump(sorted(state.blocked_domains), f, indent=2)
        logger.debug(f"Blocklist persisted ({len(state.blocked_domains)} domains): {BLOCKLIST_PATH}")
    except Exception as e:
        logger.error(f"Failed to persist blocklist: {e}")

async def _jina_http_fetch(url: str, client: httpx.AsyncClient, state: ResearchState) -> dict | None:
    """Raw single-URL Jina Reader GET. No caching."""
    try:
        response = await client.get(f"https://r.jina.ai/{url}")
        response.raise_for_status()
        return {"url": url, "content": response.text, "title": ""}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 451:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if domain not in state.blocked_domains:
                state.blocked_domains.add(domain)
                _persist_blocklist(state)
                logger.warning(f"HTTP 451 for {url} — domain '{domain}' blocked.")
        else:
            logger.warning(f"Jina fetch failed for {url}: HTTP {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Jina fetch failed for {url}: {e}")
        return None


async def _tinyfish_http_fetch(url: str, client: httpx.AsyncClient) -> dict | None:
    """Raw single-URL TinyFish POST. No caching."""
    if not TINYFISH_API_KEY:
        logger.warning("TinyFish fetch skipped: TINYFISH_API_KEY not set.")
        return None
    try:
        response = await client.post(
            "https://api.fetch.tinyfish.ai",
            headers={"X-API-Key": TINYFISH_API_KEY, "Accept": "application/json"},
            json={"urls": [url], "format": "markdown"},
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"TinyFish fetch failed for {url}: {e}")
        return None

    for res in data.get("results", []):
        content = res.get("text", "")
        if content:
            return {"url": url, "content": content, "title": res.get("title", "")}

    for err in data.get("errors", []):
        logger.warning(f"TinyFish fetch error for {url}: {err.get('error')} (status {err.get('status')})")
    return None


async def _fetch_single_fallback(url: str, client: httpx.AsyncClient, state: ResearchState) -> dict | None:
    """
    Fetches a single URL via FETCH_FALLBACK_PROVIDER.
    Checks the fallback provider's cache first, then issues an HTTP request.
    On success, populates both provider caches so the primary finds it next run.
    Returns a result dict or None.
    """
    if FETCH_FALLBACK_PROVIDER == "jina":
        own_cache, cross_cache = _jina_cache, _tinyfish_cache
        http_coro = _jina_http_fetch(url, client, state)
        name = "jina"
    elif FETCH_FALLBACK_PROVIDER == "tinyfish":
        own_cache, cross_cache = _tinyfish_cache, _jina_cache
        http_coro = _tinyfish_http_fetch(url, client)
        name = "tinyfish"
    else:
        return None

    cached = own_cache.get(url)
    if cached is not None:
        logger.debug(f"Fallback ({name}) cache HIT: {url}")
        return {"url": url, "content": cached["content"], "title": cached.get("title", "")}

    result = await http_coro
    if result and result.get("content"):
        entry = {"content": result["content"], "title": result.get("title", "")}
        own_cache.set(url, entry)
        cross_cache.set(url, entry)
        logger.debug(f"Fallback ({name}) succeeded for {url}")
    return result


async def _run_tinyfish_extractor(
    state: ResearchState,
    content_queue: asyncio.Queue | None = None,
    url_queue: asyncio.Queue | None = None,
) -> AsyncGenerator[Union[dict, ResearchState], None]:
    """
    TinyFish Fetch provider — batched POST replacement for Jina Reader.
    Sends up to TINYFISH_FETCH_BATCH_SIZE URLs per request to
    https://api.fetch.tinyfish.ai, caches results in tinyfish_cache.json,
    and feeds content_queue with the same contract as the Jina path.
    """
    if not TINYFISH_API_KEY:
        logger.error("TINYFISH_API_KEY is not set. Cannot use TinyFish Fetch provider.")
        yield state
        return

    # Build the ordered list of URLs to process
    processed_urls = {f.source_url for f in state.extracted_facts if f.source_url}
    url_query_map = {res["url"]: res.get("query") for res in state.search_results}

    if url_queue:
        # Drain the url_queue into a flat list so we can batch it
        queued_urls: list[dict] = []
        while True:
            item = await url_queue.get()
            if item is None:
                break
            queued_urls.append(item)
        candidate_urls = [
            item["url"] for item in queued_urls
            if item["url"] not in processed_urls
        ]
    else:
        candidate_urls = [u for u in state.urls if u not in processed_urls]

    if not candidate_urls:
        if content_queue:
            await content_queue.put(None)
        yield state
        return

    from llm import llm

    extraction_results: list[dict] = []

    # Check cache and build the list of URLs that still need fetching
    uncached: list[str] = []
    for url in candidate_urls:
        cached = _tinyfish_cache.get(url)
        if cached is not None:
            logger.debug(f"TinyFish Fetch cache HIT: {url}")
            entry = {"url": url, "content": cached["content"], "title": cached.get("title", "")}
            extraction_results.append(entry)
            if content_queue:
                await content_queue.put({
                    "url": url,
                    "content": cached["content"],
                    "query": url_query_map.get(url) or state.user_query,
                })
        else:
            uncached.append(url)

    # Emit one pulse per cached hit so progress tracking is accurate
    for _ in extraction_results:
        yield {"status": "extracting", "unit": "io", "message": "Extraction: Fetching and parsing markdown from sources"}

    # Batch-fetch the uncached URLs
    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for batch_index, batch_start in enumerate(range(0, len(uncached), TINYFISH_FETCH_BATCH_SIZE)):
            batch = uncached[batch_start: batch_start + TINYFISH_FETCH_BATCH_SIZE]
            await _tinyfish_fetch_limiter.acquire(len(batch))
            try:
                response = await client.post(
                    "https://api.fetch.tinyfish.ai",
                    headers=headers,
                    json={"urls": batch, "format": "markdown"},
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error(f"TinyFish Fetch batch request failed: {e}")
                # Yield a pulse for each URL in the failed batch so progress doesn't stall
                for _ in batch:
                    yield {"status": "extracting", "unit": "io", "message": "Extraction: Fetching and parsing markdown from sources"}
                continue

            for res in data.get("results", []):
                url = res["url"]
                content = res.get("text", "")
                title = res.get("title", "")
                if not content:
                    continue
                _tinyfish_cache.set(url, {"content": content, "title": title})
                entry = {"url": url, "content": content, "title": title}
                extraction_results.append(entry)
                if content_queue:
                    await content_queue.put({
                        "url": url,
                        "content": content,
                        "query": url_query_map.get(url) or state.user_query,
                    })
                yield {"status": "extracting", "unit": "io", "message": "Extraction: Fetching and parsing markdown from sources"}

            for err in data.get("errors", []):
                err_url = err.get("url", "")
                logger.warning(f"TinyFish Fetch error for {err_url}: {err.get('error')} (status {err.get('status')})")

                if FETCH_FALLBACK_PROVIDER != "none" and err_url:
                    fallback_result = await _fetch_single_fallback(err_url, client, state)
                    if fallback_result:
                        extraction_results.append(fallback_result)
                        if content_queue:
                            await content_queue.put({
                                "url": err_url,
                                "content": fallback_result["content"],
                                "query": url_query_map.get(err_url) or state.user_query,
                            })

                yield {"status": "extracting", "unit": "io", "message": "Extraction: Fetching and parsing markdown from sources"}

    if content_queue:
        await content_queue.put(None)

    found_results = [r for r in extraction_results if r.get("content")]
    logger.debug(f"TinyFish Fetch successfully extracted {len(found_results)} sources.")

    state.raw_content = [
        {
            "url": r["url"],
            "content": r["content"],
            "query": url_query_map.get(r["url"]),
        }
        for r in found_results
    ]

    # Store for replay (same pattern as Jina)
    try:
        async with llm.counter_lock:
            llm.inference_counter += 1
            current_index = llm.inference_counter
        filepath = os.path.join(llm.log_dir, f"{current_index:04d}_ExtractorData_output.json")
        with open(filepath, "w") as f:
            json.dump({"raw_content": state.raw_content}, f, indent=2)
        logger.debug(f"TinyFish Fetch logged for replay: {filepath}")
    except Exception as log_err:
        logger.error(f"Failed to log ExtractorData: {log_err}")

    yield state


async def run_extractor(state: ResearchState, content_queue: asyncio.Queue | None = None, url_queue: asyncio.Queue | None = None) -> AsyncGenerator[Union[dict, ResearchState], None]:
    """
    Dispatcher: routes extraction to TinyFish Fetch or Jina Reader based on FETCH_PROVIDER.
    Yields progress updates and finally the populated state.raw_content.
    """
    if FETCH_PROVIDER == "tinyfish":
        async for item in _run_tinyfish_extractor(state, content_queue, url_queue):
            yield item
        return

    if not state.urls:
        logger.warning("No URLs provided to run_extractor.")
        yield state
        return
    # 1. Deduplicate by skipping already processed URLs
    processed_urls = {f.source_url for f in state.extracted_facts if f.source_url}
    urls_to_process = [u for u in state.urls if u not in processed_urls] if state.urls else []
    
    if not url_queue and not urls_to_process:
        state.raw_content = []
        yield state
        return

    logger.debug("Extracting content from URLs via Jina Reader.")

    # Create a mapping of URL -> Query for lookups
    url_query_map = {res["url"]: res.get("query") for res in state.search_results}
    
    # RPM-centric configuration:
    # 20 RPM is the standard free tier limit. Target 18 for safety by default.
    JINA_RPM = int(os.getenv("JINA_RPM", "18"))
    
    # Derivations:
    JINA_STAGGER_SEC = 60.0 / JINA_RPM
    # Safe concurrency: allow a small pool that scales slightly with RPM, capped for safety.
    JINA_CONCURRENCY = max(1, min(JINA_RPM // 6, 5))
    
    logger.debug(f"Jina Extraction Pacing: {JINA_RPM} RPM | {JINA_STAGGER_SEC:.2f}s stagger | {JINA_CONCURRENCY} concurrency")
    
    semaphore = asyncio.Semaphore(JINA_CONCURRENCY)
    from llm import llm

    extraction_results = []
    completed = 0
    last_start_time = 0
    pacing_lock = asyncio.Lock()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def fetch_url(url: str, index: int) -> dict | None:
                nonlocal last_start_time

                # Cache check — skip HTTP entirely if content is already stored
                cached = _jina_cache.get(url)
                if cached is not None:
                    logger.debug(f"Jina cache HIT: {url}")
                    return {"url": url, "content": cached["content"], "title": cached.get("title", "")}

                async with semaphore:
                    # Adaptive Pacing: Ensure JINA_STAGGER_SEC passes between STARTS.
                    # Placing this INSIDE the semaphore prevents 'bursting' when slots open up.
                    async with pacing_lock:
                        now = time.time()
                        elapsed = now - last_start_time
                        if elapsed < JINA_STAGGER_SEC:
                            await asyncio.sleep(JINA_STAGGER_SEC - elapsed)
                        last_start_time = time.time()

                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            # Jina Reader API: prepend r.jina.ai to the target URL
                            jina_url = f"https://r.jina.ai/{url}"
                            response = await client.get(jina_url)
                            response.raise_for_status()
                            result = {"url": url, "content": response.text, "title": ""}
                            _jina_cache.set(url, {"content": response.text, "title": ""})
                            return result
                        except httpx.HTTPStatusError as e:
                            if e.response.status_code == 451:
                                # Domain blocked by Jina (Legal) — remember and persist if new
                                domain = urlparse(url).netloc.lower().replace("www.", "")
                                if domain not in state.blocked_domains:
                                    state.blocked_domains.add(domain)
                                    _persist_blocklist(state)
                                    logger.warning(f"HTTP 451 for {url} — domain '{domain}' added to blocklist.")
                                return None
                            elif e.response.status_code == 429:
                                # Rate Limit Hit: Exponential backoff or Retry-After
                                if attempt < max_retries - 1:
                                    retry_after = e.response.headers.get("Retry-After")
                                    wait_time = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt * 5)
                                    logger.warning(f"429 Too Many Requests for {url}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                                    await asyncio.sleep(wait_time)
                                    continue
                            return None
                        except Exception as e:
                            logger.error(f"Error extracting {url}: {e}")
                            return None

            pulse_queue = asyncio.Queue()
            
            async def fetch_consumer():
                pending_tasks = set()
                
                async def process_task(url: str, index: int):
                    res = await fetch_url(url, index)

                    if res is None and FETCH_FALLBACK_PROVIDER != "none":
                        res = await _fetch_single_fallback(url, client, state)

                    if res:
                        extraction_results.append(res)
                        if content_queue:
                            item = {
                                "url": res["url"],
                                "content": res["content"],
                                "query": url_query_map.get(res["url"]) or state.user_query
                            }
                            await content_queue.put(item)

                    await pulse_queue.put({
                        "status": "extracting",
                        "unit": "io",
                        "message": f"Extraction: Fetching and parsing markdown from sources"
                    })

                if url_queue:
                    index = 0
                    while True:
                        url_item = await url_queue.get()
                        if url_item is None:
                            break
                        url = url_item["url"]
                        
                        # Apply pre-filters
                        if url in processed_urls:
                            await pulse_queue.put({"status": "extracting", "units_discovered": -1, "unit_type": "io", "message": "Extraction: URL already processed"})
                            continue
                        domain = urlparse(url).netloc.lower().replace("www.", "")
                        if state.blocked_domains and domain in state.blocked_domains:
                            await pulse_queue.put({"status": "extracting", "units_discovered": -1, "unit_type": "io", "message": "Extraction: Domain blocked"})
                            continue

                        task = asyncio.create_task(process_task(url, index))
                        pending_tasks.add(task)
                        task.add_done_callback(pending_tasks.discard)
                        index += 1
                else:
                    skipped = len(state.urls) - len(urls_to_process)
                    if skipped > 0:
                        await pulse_queue.put({"status": "extracting", "units_discovered": -skipped, "unit_type": "io", "message": f"Extraction: Skipped {skipped} previously processed URLs"})

                    for i, u in enumerate(urls_to_process):
                        domain = urlparse(u).netloc.lower().replace("www.", "")
                        if state.blocked_domains and domain in state.blocked_domains:
                            await pulse_queue.put({"status": "extracting", "units_discovered": -1, "unit_type": "io", "message": "Extraction: Domain blocked"})
                            continue
                            
                        task = asyncio.create_task(process_task(u, i))
                        pending_tasks.add(task)
                        task.add_done_callback(pending_tasks.discard)

                if pending_tasks:
                    await asyncio.gather(*pending_tasks)
                
                if content_queue:
                    await content_queue.put(None)
                    
                await pulse_queue.put(None)

            consumer_task = asyncio.create_task(fetch_consumer())

            while True:
                pulse = await pulse_queue.get()
                if pulse is None:
                    break
                yield pulse
                
            await consumer_task
            
            # Post-cleanup and logging
            found_results = [r for r in extraction_results if r and r.get("content")]
            logger.debug(f"Jina successfully extracted {len(found_results)} sources.")
            
            state.raw_content = [
                {
                    "url": r["url"], 
                    "content": r["content"],
                    "query": url_query_map.get(r["url"]) # Preserve the targeted query
                } for r in found_results
            ]

            # Store for replay
            try:
                async with llm.counter_lock:
                    llm.inference_counter += 1
                    current_index = llm.inference_counter
                filepath = os.path.join(llm.log_dir, f"{current_index:04d}_ExtractorData_output.json")
                with open(filepath, "w") as f:
                    json.dump({"raw_content": state.raw_content}, f, indent=2)
                logger.debug(f"Jina Extract logged for replay: {filepath}")
            except Exception as log_err:
                logger.error(f"Failed to log ExtractorData: {log_err}")

            yield state

    except Exception as e:
        logger.error(f"Error in run_extractor: {e}")
        yield state


