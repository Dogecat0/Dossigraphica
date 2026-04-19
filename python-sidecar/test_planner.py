"""
Dry-run verification: tests that the deterministic planner generates
the correct number and format of search queries without any LLM calls.
"""
import asyncio
import os
import sys

# Load .env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from schemas import ResearchState
from tasks.planner import run_planner, SEARCHABLE_FIELDS, _get_temporal_anchors


async def test_planner():
    lookback = int(os.getenv("QUARTER_LOOKBACK", "1"))
    temporal_anchors = _get_temporal_anchors(lookback)
    expected_count = len(SEARCHABLE_FIELDS) * len(temporal_anchors)

    print(f"QUARTER_LOOKBACK = {lookback}")
    print(f"SEARCHABLE_FIELDS = {len(SEARCHABLE_FIELDS)}")
    print(f"Temporal anchors = {temporal_anchors}")
    print(f"Expected query count = {expected_count}")
    print()

    state = ResearchState(user_query="ASML")
    state = await run_planner(state)

    print(f"Actual query count = {len(state.search_queries)}")
    print()
    for i, q in enumerate(state.search_queries, 1):
        print(f"  [{i:02d}] {q}")

    print()

    # Assertions
    assert len(state.search_queries) == expected_count, (
        f"FAIL: Expected {expected_count} queries, got {len(state.search_queries)}"
    )

    for q in state.search_queries:
        assert "ASML" in q, f"FAIL: Query missing user_query: {q}"

    # Verify no rigid calendar-quarter labels like "Q1 2026" leaked in
    import re
    for q in state.search_queries:
        assert not re.search(r'\bQ[1-4]\s+\d{4}\b', q), (
            f"FAIL: Rigid quarter label found in query: {q}"
        )

    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(test_planner())
