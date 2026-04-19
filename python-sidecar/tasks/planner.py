import os
import logging
from datetime import datetime
from schemas import ResearchState, GeoIntelligenceSchema

logger = logging.getLogger(__name__)

# Fields from GeoIntelligenceSchema that represent searchable intelligence targets.
# Metadata fields (company, ticker, website, sector, description, anchorFiling,
# generatedDate) are excluded — they don't generate useful search queries.
SEARCHABLE_FIELDS = [
    "offices",
    "revenueGeography",
    "supplyChain",
    "customerConcentration",
    "geopoliticalRisks",
    "expansionSignals",
    "contractionSignals",
]

# Relative temporal phrases indexed by lookback depth.
# These are fiscal-calendar-agnostic — companies have arbitrary fiscal years,
# so we never hardcode "Q2 2026". Instead, we use relative language that lets
# the search engine surface the most recent filings naturally.
_TEMPORAL_ANCHORS = [
    "latest earnings report/call transcript",
]


def _get_temporal_anchors(lookback: int) -> list[str]:
    """
    Return the first `lookback` relative temporal phrases.

    Unlike rigid calendar-quarter labels, these are company-agnostic and
    work regardless of whether the target's fiscal year starts in January,
    April, or October.
    """
    current_year = datetime.now().year
    anchors: list[str] = []
    for i in range(min(lookback, len(_TEMPORAL_ANCHORS))):
        # Append the current year so the search engine biases toward recency,
        # but without locking to a specific quarter boundary.
        anchors.append(f"{_TEMPORAL_ANCHORS[i]} {current_year}")
    return anchors


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
    temporal_anchors = _get_temporal_anchors(lookback)

    logger.info(
        f"Programmatic Planner: {len(SEARCHABLE_FIELDS)} fields × "
        f"{len(temporal_anchors)} temporal anchor(s) = "
        f"{len(SEARCHABLE_FIELDS) * len(temporal_anchors)} queries"
    )

    queries: list[str] = []
    for field_name in SEARCHABLE_FIELDS:
        field_info = GeoIntelligenceSchema.model_fields[field_name]
        description = field_info.description or field_name

        for anchor in temporal_anchors:
            query = f"{state.user_query} {description} {anchor}"
            queries.append(query)

    state.search_queries = queries
    state.scratchpad += (
        f"\n## Programmatic Research Plan\n"
        f"Generated {len(queries)} queries from schema introspection.\n"
        f"Temporal anchors: {temporal_anchors}\n"
    )

    logger.info(f"Planner generated {len(queries)} deterministic queries.")
    return state
