import asyncio
import os
import json
import logging
from schemas import ResearchState, SingleTriageSchema
from llm import llm, LLAMA_N_PARALLEL

logger = logging.getLogger(__name__)


async def run_source_triage(state: ResearchState) -> ResearchState:
    """
    LLM-based source triage: concurrent map-reduce over search result snippets.
    Each URL+snippet is evaluated independently by the LLM against a binary
    authoritative/spam schema. Only URLs that pass survive into state.urls.
    """
    if not state.search_results:
        logger.warning("No search results to triage.")
        return state

    total = len(state.search_results)
    logger.info(f"Source triage starting: {total} URLs to evaluate.")

    # ------------------------------------------------------------------
    # Semaphore: slightly higher than LLAMA_N_PARALLEL to keep the
    # llama.cpp queue saturated without over-committing memory.
    # The LLMClient's own semaphore is the true bottleneck guard.
    # ------------------------------------------------------------------
    triage_semaphore = asyncio.Semaphore(LLAMA_N_PARALLEL + 2)

    async def evaluate_single(result: dict) -> dict | None:
        """Evaluate a single search result; returns it if authoritative, else None."""
        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("content", "")

        prompt = (
            f"Evaluate the following search result.\n\n"
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"Snippet: {snippet}\n\n"
            f"Return True if this is an authoritative, high-signal source "
            f"(e.g., SEC Filings, Official Earnings Call Transcripts, Investor Presentations, Bloomberg, WSJ, Reuters, FT, major financial journal, established industry publication).\n"
            f"Return False if this looks like SEO spam, PR wire aggregation, "
            f"a generic content mill, a social media post, or a low-quality blog."
        )

        system_prompt = (
            "You are a ruthless source quality filter for a financial intelligence pipeline. "
            "Your only job is to decide whether a single URL is worth fetching. "
            "Be aggressive: when in doubt, reject."
        )

        async with triage_semaphore:
            try:
                verdict = await llm.generate_structured(
                    prompt=prompt,
                    response_model=SingleTriageSchema,
                    system_prompt=system_prompt,
                )
                if verdict.is_authoritative:
                    logger.info(f"  PASS: {url}")
                    return result
                else:
                    logger.info(f"  REJECT: {url} — {verdict.reasoning[:80]}")
                    return None
            except Exception as e:
                logger.error(f"  ERROR triaging {url}: {e}. Keeping URL as fallback.")
                # On LLM failure, keep the URL rather than silently drop data
                return result

    # ------------------------------------------------------------------
    # Concurrent map: evaluate all search results in parallel
    # ------------------------------------------------------------------
    tasks = [evaluate_single(r) for r in state.search_results]
    results = await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Reduce: aggregate surviving URLs, deduplicate
    # ------------------------------------------------------------------
    seen_urls: set[str] = set()
    surviving_results: list[dict] = []

    for r in results:
        if r is not None:
            url = r["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                surviving_results.append(r)

    # Reassign curated state
    state.search_results = surviving_results
    state.urls = [r["url"] for r in surviving_results]

    logger.info(
        f"Source triage complete: {len(surviving_results)}/{total} URLs survived."
    )

    # ------------------------------------------------------------------
    # Store aggregated triage output for log replay
    # ------------------------------------------------------------------
    try:
        async with llm.counter_lock:
            llm.inference_counter += 1
            current_index = llm.inference_counter

        filepath = os.path.join(
            llm.log_dir, f"{current_index:04d}_TriageData_output.json"
        )
        with open(filepath, "w") as f:
            json.dump(
                {
                    "surviving_urls": state.urls,
                    "total_evaluated": total,
                    "total_survived": len(surviving_results),
                },
                f,
                indent=2,
            )
        logger.info(f"Triage data logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log TriageData: {e}")

    return state
