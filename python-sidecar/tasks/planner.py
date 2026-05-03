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

    Generates search queries as the Cartesian product of:
      - GeoIntelligenceSchema searchable field descriptions
      - Relative temporal anchors (derived from QUARTER_LOOKBACK env var)

    No LLM is used. Query count is bounded:
      len(SEARCHABLE_FIELDS) × QUARTER_LOOKBACK
    """
    lookback = int(os.getenv("QUARTER_LOOKBACK", "1"))
    quarters_block = _get_rigid_quarters_block(lookback)

    logger.info(
        f"Programmatic Planner: {len(SEARCHABLE_FIELDS)} fields. "
        f"Temporal block: {quarters_block}"
    )

    queries: list[str] = []
    for field_name in SEARCHABLE_FIELDS:
        field_info = GeoIntelligenceSchema.model_fields[field_name]
        description = field_info.description or field_name

        # Single query per field containing all requested time markers
        query = f"{state.user_query} {description} {quarters_block}"
        queries.append(query)

    state.search_queries = queries
    state.scratchpad += (
        f"\n## Programmatic Research Plan\n"
        f"Generated {len(queries)} queries from schema introspection.\n"
        f"Rigid Quarters: {quarters_block}\n"
    )

    logger.debug(f"Planner generated {len(queries)} deterministic queries.")
    return state
