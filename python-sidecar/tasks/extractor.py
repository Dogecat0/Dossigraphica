import httpx
import os
from schemas import ResearchState
import logging

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

async def run_extractor(state: ResearchState) -> ResearchState:
    """
    Managed extraction utilizing the Tavily API to grab raw markdown from targets.
    Populates state.raw_content with extracted data.
    """
    if not state.urls:
        logger.warning("No URLs provided to run_extractor.")
        return state

    if not TAVILY_API_KEY:
        logger.error("TAVILY_API_KEY environment variable not set.")
        # Fallback logic could go here if we had a local scraper
        return state

    logger.info(f"Extracting content from {len(state.urls)} URLs via Tavily.")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.tavily.com/extract",
                headers={
                    "Authorization": f"Bearer {TAVILY_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "urls": state.urls,
                    "extract_depth": "basic"
                }
            )
            response.raise_for_status()
            extract_data = response.json()
            
            # results is an array of objects: { 'url': ..., 'raw_content': ... }
            found_results = extract_data.get("results", [])
            logger.info(f"Tavily successfully extracted {len(found_results)} sources.")
            
            state.raw_content = [
                {"url": r["url"], "content": r.get("raw_content", "")} 
                for r in found_results if r.get("raw_content")
            ]
            
            return state
            
    except Exception as e:
        logger.error(f"Error in run_extractor: {e}")
        return state
