"""
Entity Assembly — Programmatic gap detection for geographic intelligence.

Runs the same structural LLM extraction used by the drafter (get_offices,
get_supply_chain, get_risks_signals) against the current fact pool,
then inspects the Pydantic objects for missing critical geographic data
(addresses, coordinates, cities). Gaps are converted to targeted search
strings appended to ``state.enrichment_queries``.

This is a *pure inspection* step — it produces search strings, not data.
If no gaps are found, the pipeline skips the enrichment sub-loop entirely
and proceeds directly to drafting.
"""

import asyncio
import json
import logging
import os

from schemas import ResearchState
from tasks.drafter import get_offices, get_supply_chain, get_risks_signals

logger = logging.getLogger(__name__)


def _build_office_queries(offices, user_query: str) -> list[str]:
    """Generate enrichment queries for offices missing address or verified coords."""
    queries: list[str] = []
    for o in offices:
        missing_address = not o.address
        unverified_coords = o.confidence != "verified"
        if missing_address or unverified_coords:
            location_hint = " ".join(filter(None, [o.city, o.state, o.country]))
            queries.append(
                f"{user_query} {o.name} {location_hint} exact street address location coordinates"
            )
    return queries


def _build_supply_chain_queries(supply_chain, user_query: str) -> list[str]:
    """Generate enrichment queries for supply chain nodes missing city or coords."""
    queries: list[str] = []
    for n in supply_chain:
        missing_city = not n.city
        missing_coords = n.lat is None or n.lng is None
        if missing_city or missing_coords:
            location_hint = n.country or ""
            queries.append(
                f"{user_query} {n.entity} {n.role} {location_hint} exact city address coordinates"
            )
    return queries


def _build_customer_queries(customers, user_query: str) -> list[str]:
    """Generate enrichment queries for customers missing HQ city or coords."""
    queries: list[str] = []
    for c in customers:
        missing_hq = not c.hqCity
        missing_coords = c.lat is None or c.lng is None
        if missing_hq or missing_coords:
            country_hint = c.hqCountry or ""
            queries.append(
                f"{user_query} {c.customer} {country_hint} headquarters city address coordinates"
            )
    return queries


async def run_entity_assembly(state: ResearchState) -> ResearchState:
    """
    Pre-assemble Pydantic models to programmatically detect missing
    geographic data. Populate ``state.enrichment_queries`` with targeted
    search strings for the one-shot enrichment pass.
    """
    if not state.extracted_facts:
        logger.warning("No facts available for entity assembly.")
        return state

    logger.info(
        f"Entity assembly: inspecting {len(state.extracted_facts)} facts for geographic gaps."
    )

    # Run the three assembly functions in parallel against current facts
    office_result, sc_result, rs_result = await asyncio.gather(
        get_offices(state.extracted_facts, state.user_query),
        get_supply_chain(state.extracted_facts, state.user_query),
        get_risks_signals(state.extracted_facts, state.user_query),
    )

    # Programmatic gap detection
    gap_queries: list[str] = []
    gap_queries.extend(_build_office_queries(office_result.offices, state.user_query))
    gap_queries.extend(_build_supply_chain_queries(sc_result.supply_chain, state.user_query))
    gap_queries.extend(_build_customer_queries(rs_result.customerConcentration, state.user_query))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in gap_queries:
        normalized = q.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_queries.append(q)

    state.enrichment_queries = unique_queries

    logger.info(
        f"Entity assembly complete. Identified {len(unique_queries)} enrichment gaps."
    )
    if unique_queries:
        for i, q in enumerate(unique_queries):
            logger.debug(f"  Gap {i+1}: {q}")

    # ------------------------------------------------------------------
    # Store assembly output for log replay
    # ------------------------------------------------------------------
    try:
        from llm import llm

        async with llm.counter_lock:
            llm.inference_counter += 1
            current_index = llm.inference_counter

        filepath = os.path.join(
            llm.log_dir, f"{current_index:04d}_EntityAssemblyData_output.json"
        )
        with open(filepath, "w") as f:
            json.dump(
                {"enrichment_queries": state.enrichment_queries},
                f,
                indent=2,
            )
        logger.info(f"Entity assembly logged for replay: {filepath}")
    except Exception as e:
        logger.error(f"Failed to log EntityAssemblyData: {e}")

    return state
