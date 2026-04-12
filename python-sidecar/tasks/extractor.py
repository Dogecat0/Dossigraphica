import httpx
import os
import asyncio
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

async def run_extractor(state: ResearchState) -> ResearchState:
    """
    Managed extraction utilizing the Tavily API to grab raw markdown from targets.
    Populates state.raw_content with extracted data and original search queries.
    """
    if not state.urls:
        logger.warning("No URLs provided to run_extractor.")
        return state

    if not TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY environment variable not set.")
        return state

    logger.info(f"Extracting content from {len(state.urls)} URLs via Tavily in chunks of 20.")
    
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
    
    # The Tavily Extract API allows a maximum of 20 URLs per request
    chunk_size = 20
    url_chunks = [urls_to_process[i:i + chunk_size] for i in range(0, len(urls_to_process), chunk_size)]
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def fetch_chunk(urls):
                try:
                    response = await client.post(
                        "https://api.tavily.com/extract",
                        headers={
                            "Authorization": f"Bearer {TAVILY_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "urls": urls,
                            "extract_depth": "basic" # Basic extraction
                        }
                    )
                    response.raise_for_status()
                    return response.json().get("results", [])
                except Exception as e:
                    logger.error(f"Error extracting chunk of {len(urls)} URLs: {e}")
                    return []
            
            # Execute chunk requests concurrently
            tasks = [fetch_chunk(chunk) for chunk in url_chunks]
            chunk_results = await asyncio.gather(*tasks)
            
            found_results = []
            for res_list in chunk_results:
                found_results.extend(res_list)
                
            logger.info(f"Tavily successfully extracted {len(found_results)} sources.")
            
            state.raw_content = [
                {
                    "url": r["url"], 
                    "content": r.get("raw_content", ""),
                    "query": url_query_map.get(r["url"]) # Preserve the targeted query
                } 
                for r in found_results if r.get("raw_content")
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
                logger.info(f"Tavily Extract logged for replay: {filepath}")
            except Exception as log_err:
                logger.error(f"Failed to log ExtractorData: {log_err}")
            
            return state
            
    except Exception as e:
        logger.error(f"Error in run_extractor: {e}")
        return state
