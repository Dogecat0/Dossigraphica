import os
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
                raw = json.load(f)
                state.blocked_domains = {k: int(v) for k, v in raw.items()} if isinstance(raw, dict) else {d: 1 for d in raw}
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
    
    # Step ordering for monotonic resolution (never downgrade).
    _STEP_ORDER = {
        "init": 0,
        "searching": 1,
        "source_triage": 2,
        "extracting": 3,
        "preprocessing": 4,
        "entity_assembly": 5,
        "enrichment_searching": 6,
        "enrichment_extracting": 7,
        "drafting": 8,
        "completed": 9,
    }

    latest_step_resolved = "init"
    latest_order = 0

    def _resolve(step: str) -> None:
        nonlocal latest_step_resolved, latest_order
        order = _STEP_ORDER.get(step, 0)
        if order > latest_order:
            latest_step_resolved = step
            latest_order = order

    # Check for aggregate PreprocessorFacts checkpoint first.
    # This preserves source_url on every fact (the per-file SynthesizerSchema
    # logs don't include it), which is critical for correct source-url grouping.
    preproc_checkpoint = None
    for idx, filename in files:
        if "PreprocessorFacts" in filename:
            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    preproc_checkpoint = json.load(f)
            except Exception:
                pass
            break

    if preproc_checkpoint is not None:
        from schemas import InternalFact
        for fact_dict in preproc_checkpoint.get("extracted_facts", []):
            f = InternalFact(
                reason=fact_dict.get("reason", ""),
                content=fact_dict.get("content", ""),
                category=fact_dict.get("category", "UNKNOWN"),
                source_url=fact_dict.get("source_url", ""),
            )
            state.extracted_facts.append(f)

    for idx, filename in files:
        filepath = os.path.join(log_dir, filename)
        if "PreprocessorFacts" in filename:
            continue  # already loaded above
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception:
            continue
            
        if "PlannerSchema" in filename:
            state.search_queries = data.get("search_queries", [])
            _resolve("searching")

        elif "SearchData" in filename:
            state.search_results = data.get("search_results", [])
            state.urls = data.get("urls", [])
            _resolve("source_triage")
        elif "TriageData" in filename:
            surviving_urls = data.get("surviving_urls", [])
            if surviving_urls:
                state.urls = surviving_urls
                # Filter search_results to match surviving URLs
                surviving_set = set(surviving_urls)
                state.search_results = [
                    r for r in state.search_results if r.get("url") in surviving_set
                ]
            _resolve("extracting")
        elif "ExtractorData" in filename:
            state.raw_content = data.get("raw_content", [])
            _resolve("preprocessing")

        elif "SynthesizerSchema" in filename:
            # Reconstruct facts from individual LLM outputs ONLY when there
            # is no aggregate PreprocessorFacts checkpoint (which carries
            # source_url — SynthesizerSchema logs don't).
            if preproc_checkpoint is None and "extracted_facts" in data:
                from schemas import InternalFact
                for fact_dict in data["extracted_facts"]:
                    f = InternalFact(
                        reason=fact_dict.get("reason", ""),
                        content=fact_dict.get("content", ""),
                        category=fact_dict.get("category", "UNKNOWN"),
                        source_url=fact_dict.get("source_url", ""),
                    )
                    state.extracted_facts.append(f)
            _resolve("entity_assembly")

        elif "EntityAssemblyData" in filename:
            state.enrichment_queries = data.get("enrichment_queries", [])
            if state.enrichment_queries:
                _resolve("enrichment_searching")
            else:
                _resolve("drafting")

        elif "DraftingCompleteData" in filename:
            # Full drafting outputs available — skip straight to completed
            state.final_report_json = data.get("final_report_json")
            state.final_report_md = data.get("final_report_md", "")
            _resolve("completed")

        elif "EnrichmentCompleteData" in filename:
            # Canonical post-enrichment checkpoint written by pipeline.py after
            # pipeline_sieve(6) completes.  Unambiguously signals the enrichment
            # sub-loop is done and the next step is drafting.
            _resolve("drafting")

        elif "MarkdownSectionSchema" in filename:
            # Fallback: MarkdownSectionSchema logs are only written by the drafter,
            # which only runs after the enrichment loop has fully completed.
            # This handles legacy log directories that pre-date EnrichmentCompleteData.
            _resolve("drafting")

    state.pipeline_step = latest_step_resolved

    return state
