import os
import logging
from datetime import datetime
from schemas import ResearchState, GeoIntelligenceSchema

logger = logging.getLogger(__name__)

# Fields from GeoIntelligenceSchema that represent searchable intelligence targets.
# Metadata fields (company, ticker, website, sector, description, anchorFiling,
# generatedDate) are excluded.
SEARCHABLE_FIELDS = [
    "offices",
    "revenueGeography",
    "supplyChain",
    "customerConcentration",
    "geopoliticalRisks",
]

def _get_rigid_quarters_block(lookback: int) -> str:
    """
    Generate a space-separated string of rigid quarters (e.g. "Q2-2026 Q1-2026 Q4-2025")
    mapping backward from the current date.
    """
    if lookback == 0:
        return "latest earnings report"
    now = datetime.now()
    year = now.year
    quarter = (now.month - 1) // 3 + 1
    
    quarters = []
    for _ in range(lookback):
        quarters.append(f"Q{quarter}-{year}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
            
    return " ".join(quarters)


async def run_planner(state: ResearchState) -> ResearchState:
    """
    Deterministic Programmatic Planner.

    Generates two search queries per field:
      1. Clean content query (no temporal anchor) — for structural data.
      2. Temporal-anchored query — for time-sensitive data.

    Query count: 2 × len(SEARCHABLE_FIELDS)
    """
    lookback = int(os.getenv("QUARTER_LOOKBACK", "1"))
    quarters_block = _get_rigid_quarters_block(lookback)

    logger.info(
        f"Programmatic Planner: {len(SEARCHABLE_FIELDS)} fields. "
        f"Temporal block: {quarters_block}"
    )

    queries: list[str] = []

    # For every field generate TWO queries:
    #   1. Clean content query (no temporal anchor) — finds structural data
    #      (offices, supply chain, risks) without noise from temporal keywords.
    #   2. Temporal-anchored query — finds time-sensitive data (earnings,
    #      financials) for the specified quarters.
    #
    # This is fully domain-agnostic: it doesn't know about "financial" vs
    # "operational" fields. Every field gets both a content-focused and a
    # time-focused query, so whichever applies gets the right signal.
    for field_name in SEARCHABLE_FIELDS:
        field_info = GeoIntelligenceSchema.model_fields[field_name]
        description = field_info.description or field_name

        clean_query = f"{state.user_query} {description}"
        temporal_query = f"{state.user_query} {description} {quarters_block}"
        queries.extend([clean_query, temporal_query])

    state.search_queries = queries
    state.scratchpad += (
        f"\n## Programmatic Research Plan\n"
        f"Generated {len(queries)} queries (2 per field: clean + temporal).\n"
        f"Rigid Quarters: {quarters_block}\n"
    )

    logger.debug(f"Planner generated {len(queries)} deterministic queries (2 per field).")
    return state
