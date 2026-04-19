import httpx
import os
import asyncio
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

async def run_extractor(state: ResearchState) -> ResearchState:
    """
    Managed extraction utilizing the Jina Reader API to grab raw markdown from targets.
    Populates state.raw_content with extracted data and original search queries.
    """
    if not state.urls:
        logger.warning("No URLs provided to run_extractor.")
        return state

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
            async def fetch_url(url: str, index: int):
                # Stagger requests to ensure < 20 RPM limit (1 request every ~3s)
                # We add a slight margin by using 3.1s
                await asyncio.sleep(index * 3.1)
                async with semaphore:
                    try:
                        # Jina Reader API: prepend r.jina.ai to the target URL
                        jina_url = f"https://r.jina.ai/{url}"
                        response = await client.get(jina_url)
                        response.raise_for_status()
                        
                        return {
                            "url": url,
                            "content": response.text,
                            "title": ""
                        }
                    except Exception as e:
                        logger.error(f"Error extracting URL {url} via Jina: {e}")
                        return None
            
            # Execute all extractions concurrently with semaphore and staggering
            tasks = [fetch_url(u, i) for i, u in enumerate(urls_to_process)]
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
