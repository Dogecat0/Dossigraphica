import os
import glob
import json
import re
from schemas import ResearchState

def reconstruct_state_from_logs(query: str, log_dir: str) -> ResearchState:
    """
    Parses the pure LLM inference logs to rebuild the ResearchState up to the 
    interruption point, allowing the loop to continue without re-querying.
    """
    state = ResearchState(user_query=query, pipeline_step="init")
    
    if not os.path.exists(log_dir):
        return state
        
    # Find all output JSONs and sort by prefix index
    files = []
    for f in os.listdir(log_dir):
        if f.endswith("_output.json"):
            match = re.match(r'^(\d+)_', f)
            if match:
                files.append((int(match.group(1)), f))
    
    if not files:
        return state
        
    files.sort(key=lambda x: x[0])
    
    latest_step_resolved = "init"
    
    for idx, filename in files:
        filepath = os.path.join(log_dir, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception:
            continue
            
        if "PlannerSchema" in filename:
            state.search_queries = data.get("search_queries", [])
            latest_step_resolved = "searching"

        elif "SearchData" in filename:
            state.search_results = data.get("search_results", [])
            state.urls = data.get("urls", [])
            latest_step_resolved = "source_triage"
        elif "TriageData" in filename:
            surviving_urls = data.get("surviving_urls", [])
            if surviving_urls:
                state.urls = surviving_urls
                # Filter search_results to match surviving URLs
                surviving_set = set(surviving_urls)
                state.search_results = [
                    r for r in state.search_results if r.get("url") in surviving_set
                ]
            latest_step_resolved = "extracting"
        elif "ExtractorData" in filename:
            state.raw_content = data.get("raw_content", [])
            latest_step_resolved = "preprocessing"
            
        elif "SynthesizerSchema" in filename:
            # Reconstruct the facts so the extractor knows which URLs have been fully processed
            if "extracted_facts" in data:
                from schemas import InternalFact
                for fact_dict in data["extracted_facts"]:
                    f = InternalFact(
                        content=fact_dict.get("content", ""),
                        category=fact_dict.get("category", "UNKNOWN"),
                        reasoning=fact_dict.get("reasoning", ""),
                        source_url=fact_dict.get("source_url", "")
                    )
                    state.extracted_facts.append(f)
            latest_step_resolved = "drafting"
            
    state.pipeline_step = latest_step_resolved
    return state
