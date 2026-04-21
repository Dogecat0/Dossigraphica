import os
import glob
import json
import re
import logging
from schemas import ResearchState

def reconstruct_state_from_logs(query: str, log_dir: str) -> ResearchState:
    """
    Parses the pure LLM inference logs to rebuild the ResearchState up to the 
    interruption point, allowing the loop to continue without re-querying.
    """
    state = ResearchState(user_query=query, pipeline_step="init")

    # Load persisted domain blocklist (stored at sidecar root, survives log wipes)
    blocklist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blocked_domains.json")
    if os.path.exists(blocklist_path):
        try:
            with open(blocklist_path, "r") as f:
                state.blocked_domains = set(json.load(f))
            if state.blocked_domains:
                logging.getLogger(__name__).info(
                    f"Loaded {len(state.blocked_domains)} blocked domains from disk: {state.blocked_domains}"
                )
        except Exception:
            pass  # Non-critical: start with empty set on corruption
    
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
            latest_step_resolved = "entity_assembly"

        elif "EntityAssemblyData" in filename:
            state.enrichment_queries = data.get("enrichment_queries", [])
            if state.enrichment_queries:
                latest_step_resolved = "enrichment_searching"
            else:
                latest_step_resolved = "drafting"

        elif "EnrichmentCompleteData" in filename:
            # Canonical post-enrichment checkpoint written by pipeline.py after
            # pipeline_sieve(6) completes.  Unambiguously signals the enrichment
            # sub-loop is done and the next step is drafting.
            latest_step_resolved = "drafting"

        elif "MarkdownSectionSchema" in filename:
            # Fallback: MarkdownSectionSchema logs are only written by the drafter,
            # which only runs after the enrichment loop has fully completed.
            # This handles legacy log directories that pre-date EnrichmentCompleteData.
            latest_step_resolved = "drafting"

    state.pipeline_step = latest_step_resolved

    return state
