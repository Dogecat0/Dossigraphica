import httpx
import os
import asyncio
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

JINA_API_KEY = os.getenv("JINA_API_KEY")

async def run_extractor(state: ResearchState) -> ResearchState:
    """
    Managed extraction utilizing the Jina Reader API to grab raw markdown from targets.
    Populates state.raw_content with extracted data and original search queries.
    """
    if not state.urls:
        logger.warning("No URLs provided to run_extractor.")
        return state

    if not JINA_API_KEY:
        logger.warning("JINA_API_KEY environment variable not set. Using Jina Reader without a key (lower rate limits).")

    logger.info(f"Extracting content from {len(state.urls)} URLs via Jina Reader.")
    
    # 1. Deduplicate by skipping already processed URLs
    processed_urls = {f.source_url for f in state.extracted_facts if f.source_url}
    urls_to_process = [u for u in state.urls if u not in processed_urls]
    
    if not urls_to_process:
        logger.info("All target URLs have already been extracted in previous loops. Skipping.")
        state.raw_content = []
        return state
        
    logger.info(f"After filtering, {len(urls_to_process)} NEW URLs will be extracted.")
    
    # Create a mapping of URL -> Query for lookups
    url_query_map = {res["url"]: res.get("query") for res in state.search_results}
    
    # Semaphore to control concurrency and avoid hitting Jina rate limits.
    # 5 concurrent requests is a safe "steady drip" for the free tier (20 RPM).
    semaphore = asyncio.Semaphore(5)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def fetch_url(url: str):
                async with semaphore:
                    try:
                        headers = {
                            "Accept": "application/json",
                            "X-With-Links-Summary": "true"
                        }
                        if JINA_API_KEY:
                            headers["Authorization"] = f"Bearer {JINA_API_KEY}"
                        
                        # Jina Reader API: prepend r.jina.ai to the target URL
                        jina_url = f"https://r.jina.ai/{url}"
                        response = await client.get(jina_url, headers=headers)
                        response.raise_for_status()
                        
                        result = response.json()
                        if result.get("code") == 200 and result.get("data"):
                            data = result["data"]
                            return {
                                "url": url,
                                "content": data.get("content", ""),
                                "title": data.get("title", "")
                            }
                        return None
                    except Exception as e:
                        logger.error(f"Error extracting URL {url} via Jina: {e}")
                        return None
            
            # Execute all extractions concurrently with semaphore
            tasks = [fetch_url(u) for u in urls_to_process]
            extraction_results = await asyncio.gather(*tasks)
            
            # Filter out failed extractions
            found_results = [r for r in extraction_results if r and r.get("content")]
                
            logger.info(f"Jina successfully extracted {len(found_results)} sources.")
            
            state.raw_content = [
                {
                    "url": r["url"], 
                    "content": r["content"],
                    "query": url_query_map.get(r["url"]) # Preserve the targeted query
                } 
                for r in found_results
            ]
            
            # Store for replay
            from llm import llm
            import json
            try:
                async with llm.counter_lock:
                    llm.inference_counter += 1
                    current_index = llm.inference_counter
                    
                filepath = os.path.join(llm.log_dir, f"{current_index:04d}_ExtractorData_output.json")
                with open(filepath, "w") as f:
                    json.dump({
                        "raw_content": state.raw_content
                    }, f, indent=2)
                logger.info(f"Jina Extract logged for replay: {filepath}")
            except Exception as log_err:
                logger.error(f"Failed to log ExtractorData: {log_err}")
            
            return state
            
    except Exception as e:
        logger.error(f"Error in run_extractor: {e}")
        return state
