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
    
    # 1. Draft the Markdown Report (narrative first helps the model organize thoughts)
    md_prompt = (
        f"Generate a professional deep research report for: {state.user_query}\n\n"
        f"FACTS:\n{facts_text}\n\n"
        "Sections: Executive Summary, Supply Chain, Geopolitical Risk, Strategic Outlook."
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
            generatedDate: str

        basic_info = await draft_section(
            f"Extract basic company details for {state.user_query} from these facts:\n{facts_text}",
            BasicInfo,
            "You are a precision data extractor."
        )

        # B. Anchor Filing
        anchor = await draft_section(
            f"Identify the primary source filing (e.g. 10-K) from these facts:\n{facts_text}",
            AnchorFilingSchema,
            "Extract anchor filing details."
        )

        # C. Offices
        class OfficeList(BaseModel):
            offices: List[OfficeSchema]

        offices_data = await draft_section(
            f"Extract all physical office locations from these facts:\n{facts_text}",
            OfficeList,
            "Extract office locations into the schema."
        )

        # D. Revenue Geography
        revenue = await draft_section(
            f"Extract revenue breakdown by geography from these facts:\n{facts_text}",
            RevenueGeographySchema,
            "Extract revenue geography."
        )

        # E. Supply Chain
        class SupplyChainList(BaseModel):
            supply_chain: List[SupplyChainNodeSchema]

        sc_data = await draft_section(
            f"Extract supply chain partners and roles from these facts:\n{facts_text}",
            SupplyChainList,
            "Extract supply chain nodes."
        )

        # F. Risks & Signals (Simplified for this stage)
        class RisksAndSignals(BaseModel):
            geopoliticalRisks: List[GeopoliticalRiskSchema]
            expansionSignals: List[ExpansionSignalSchema]
            contractionSignals: List[ContractionSignalSchema]
            customerConcentration: List[CustomerNodeSchema]

        rs_data = await draft_section(
            f"Extract risks, customers, and expansion/contraction signals:\n{facts_text}",
            RisksAndSignals,
            "Extract risks and signals."
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
