import httpx
import os
import json
import asyncio
import time
from typing import AsyncGenerator, Union
from urllib.parse import urlparse
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

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

async def run_extractor(state: ResearchState, content_queue: asyncio.Queue | None = None, url_queue: asyncio.Queue | None = None) -> AsyncGenerator[Union[dict, ResearchState], None]:
    """
    Managed extraction utilizing the Jina Reader API to grab raw markdown from targets.
    Yields progress updates and finally the populated state.raw_content.
    """
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

    logger.info("Extracting content from URLs via Jina Reader.")

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
                            return {"url": url, "content": response.text, "title": ""}
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
            logger.info(f"Jina successfully extracted {len(found_results)} sources.")
            
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
                logger.info(f"Jina Extract logged for replay: {filepath}")
            except Exception as log_err:
                logger.error(f"Failed to log ExtractorData: {log_err}")

            yield state

    except Exception as e:
        logger.error(f"Error in run_extractor: {e}")
        yield state


