from schemas import (
    ResearchState, GeoIntelligenceSchema, OfficeSchema, SupplyChainNodeSchema, 
    CustomerNodeSchema, GeopoliticalRiskSchema, ExpansionSignalSchema, 
    ContractionSignalSchema, RevenueGeographySchema, AnchorFilingSchema
)
from llm import llm
import logging
from typing import List, Type, TypeVar
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

async def draft_section(prompt: str, response_model: Type[T], system_prompt: str) -> T:
    """Helper to draft a single section with retries."""
    return await llm.generate_structured(
        prompt=prompt,
        response_model=response_model,
        system_prompt=system_prompt
    )

async def run_drafter(state: ResearchState) -> ResearchState:
    """
    Iterative multi-stage drafting to populate the GeoIntelligenceSchema.
    Breaks down the complex schema into manageable chunks.
    """
    if not state.extracted_facts:
        logger.warning("No facts available to draft report.")
        return state

    logger.info("Drafting final reports (Multi-Stage).")
    facts_text = "\n".join([f"- {fact}" for fact in state.extracted_facts])
    
    # 1. Draft the Markdown Report (Narrative Geographic Intelligence Brief)
    md_prompt = (
        f"Act as a Senior Geo-Intelligence Analyst. Generate a professional Markdown Brief for: {state.user_query}\n\n"
        f"FACTS:\n{facts_text}\n\n"
        "Strictly use the following Narrative Framework:\n"
        "## 1. Geographic Profile Summary\n"
        "## 2. MODULE A: Corporate Footprint — Offices, Facilities & Subsidiaries\n"
        "## 3. MODULE B: Revenue Geography — Regional Segment Breakdown\n"
        "## 4. MODULE C: Supply Chain & Manufacturing Map\n"
        "## 5. MODULE D: Customer Concentration Geography\n"
        "## 6. MODULE E: Regulatory & Geopolitical Risk Map\n"
        "## 7. MODULE F: Strategic Expansion & Contraction Signals\n\n"
        "Style Guidelines:\n"
        "- Tone: Professional, objective, institutional, and forensic.\n"
        "- Precision: Use exact figures from filings. Do not round.\n"
        "- Citations: Append citations sequentially [1] after every geographic claim.\n"
        "- Works Cited: Include a numbered list at the end."
    )
    state.final_report_md = await llm.generate_text(md_prompt)
    logger.info("Markdown report completed.")

    # 2. Multi-Stage JSON Drafting
    try:
        # A. Basic Info
        class BasicInfo(BaseModel):
            company: str
            ticker: str
            website: str
            sector: str
            description: str
            generatedDate: str # ISO 8601 YYYY-MM-DD

        basic_info = await draft_section(
            f"Extract basic company details for {state.user_query} from these facts:\n{facts_text}\n\n"
            "Requirement: description must emphasize global geographic footprint. generatedDate must be YYYY-MM-DD.",
            BasicInfo,
            "You are a precision Geo-Intelligence data extractor."
        )

        # B. Anchor Filing
        anchor = await draft_section(
            f"Identify the primary source filing (e.g. 10-K) from these facts:\n{facts_text}\n\n"
            "Extract: type (10-K/10-Q/8-K), date (YYYY-MM-DD), and fiscalPeriod (e.g. FY2025).",
            AnchorFilingSchema,
            "Extract anchor filing details with ISO dates."
        )

        # C. Offices
        class OfficeList(BaseModel):
            offices: List[OfficeSchema]

        offices_data = await draft_section(
            f"Extract all physical office locations (HQ, R&D, manufacturing) from these facts:\n{facts_text}\n\n"
            "Requirements:\n"
            "- Coordinates must be decimal degrees.\n"
            "- id must be slug: {ticker}-{city}-{type}.\n"
            "- confidence must be 'verified' (Tier 1 source) or 'unverified'.",
            OfficeList,
            "Extract geographic office data for the globe application."
        )

        # D. Revenue Geography
        revenue = await draft_section(
            f"Extract revenue breakdown by geography from these facts:\n{facts_text}\n\n"
            "Requirements:\n"
            "- totalRevenue must be a raw number (e.g. 63900000000, not '$63.9B').\n"
            "- percentage must be a decimal (0.00 to 1.00).",
            RevenueGeographySchema,
            "Extract revenue geography with raw numerical precision."
        )

        # E. Supply Chain
        class SupplyChainList(BaseModel):
            supply_chain: List[SupplyChainNodeSchema]

        sc_data = await draft_section(
            f"Extract supply chain partners, foundries, and manufacturing nodes from these facts:\n{facts_text}\n\n"
            "Requirements:\n"
            "- Identify 'critical' (single-source) vs 'standard' nodes.\n"
            "- Include coordinates (decimal degrees) for all nodes.",
            SupplyChainList,
            "Map the global supply chain infrastructure."
        )

        # F. Risks & Signals (Simplified for this stage)
        class RisksAndSignals(BaseModel):
            geopoliticalRisks: List[GeopoliticalRiskSchema]
            expansionSignals: List[ExpansionSignalSchema]
            contractionSignals: List[ContractionSignalSchema]
            customerConcentration: List[CustomerNodeSchema]

        rs_data = await draft_section(
            f"Extract risks, customers, and expansion/contraction signals:\n{facts_text}\n\n"
            "Requirements:\n"
            "- riskScore: 1 (Minimal) to 5 (Critical).\n"
            "- riskCategory: trade_restriction, regulatory_compliance, geopolitical_conflict, etc.\n"
            "- expansionSignals: include investment amount if available.",
            RisksAndSignals,
            "Extract geopolitical risks and strategic geographic signals."
        )

        # 3. Assemble the final GeoIntelligenceSchema
        final_json = GeoIntelligenceSchema(
            company=basic_info.company,
            ticker=basic_info.ticker,
            website=basic_info.website,
            sector=basic_info.sector,
            description=basic_info.description,
            generatedDate=basic_info.generatedDate,
            anchorFiling=anchor,
            offices=offices_data.offices,
            revenueGeography=revenue,
            supplyChain=sc_data.supply_chain,
            customerConcentration=rs_data.customerConcentration,
            geopoliticalRisks=rs_data.geopoliticalRisks,
            expansionSignals=rs_data.expansionSignals,
            contractionSignals=rs_data.contractionSignals
        )

        state.final_report_json = final_json.model_dump()
        logger.info("Structured JSON report successfully assembled.")

    except Exception as e:
        logger.error(f"Error in multi-stage drafting: {e}")
        state.final_report_json = {"error": str(e), "partial": True}
        
    return state
