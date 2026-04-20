from schemas import (
    ResearchState, GeoIntelligenceSchema, OfficeSchema, SupplyChainNodeSchema, 
    CustomerNodeSchema, GeopoliticalRiskSchema, ExpansionSignalSchema, 
    ContractionSignalSchema, RevenueGeographySchema, AnchorFilingSchema,
    MarkdownSectionSchema, STRICT_CONFIG
)
from llm import llm, LLAMA_CTX_PER_REQUEST, LLAMA_OUTPUT_RESERVATION
from utils.geocoder import geocoder
import logging
import json
import asyncio
from typing import List, Type, TypeVar, AsyncGenerator, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# --- Shared wrapper types for structured LLM output ---

class OfficeList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str | None = Field(..., description="Analysis of office distribution and site criticality.")
    offices: List[OfficeSchema]

class SupplyChainList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str | None = Field(..., description="Strategy for mapping dependencies and risk nodes.")
    supply_chain: List[SupplyChainNodeSchema]

class RisksAndSignals(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str | None = Field(..., description="Evaluation of regional stability and strategic indicators.")
    geopoliticalRisks: List[GeopoliticalRiskSchema]
    expansionSignals: List[ExpansionSignalSchema]
    contractionSignals: List[ContractionSignalSchema]
    customerConcentration: List[CustomerNodeSchema]

async def draft_section(prompt: str, response_model: Type[T], system_prompt: str) -> T:
    """Helper to draft a single section with retries."""
    return await llm.generate_structured(
        prompt=prompt,
        response_model=response_model,
        system_prompt=system_prompt
    )

async def get_fact_subset(facts: List[any], categories: List[str], prompt_template: str, system_prompt: str, response_model: Type[BaseModel]) -> str:
    """
    Filters facts by category and returns a grouped formatted string. 
    Summarizes if too large using safe string replacement (no braces).
    """
    output = []
    for cat in categories:
        filtered = [f for f in facts if f.category == cat]
        if not filtered: continue
        output.append(f"### {cat}:\n")
        output.extend([f"- {f.content} (Source: {f.source_url})\n" for f in filtered])
            
    full_facts_text = "".join(output) if output else "No specific facts found for these categories."
    
    # Calculate available token space for facts using the centralized safe size logic.
    # This accounts for the safety buffer and the response_model schema tokens.
    target_tokens = llm.calculate_safe_chunk_size(
        system_prompt=system_prompt,
        user_prompt_template=prompt_template.replace("__FACTS__", "{chunk}"),
        response_model=response_model
    )
    
    return await llm.summarize_to_fit(full_facts_text, target_tokens, system_prompt="You are a data compression specialist.")

# -----------------------------------------------------------------------
# Module-level assembly functions.
# Accept explicit (facts, user_query) so they can be reused by both
# entity_assembly.py (gap detection) and run_drafter (final assembly).
# -----------------------------------------------------------------------

def _fill(template: str, query: str = None, facts: str = None) -> str:
    """Brace-free template interpolation helper."""
    res = template
    if query: res = res.replace("__QUERY__", query)
    if facts: res = res.replace("__FACTS__", facts)
    return res


async def get_offices(facts: List, user_query: str) -> OfficeList:
    """Extract office locations from categorized facts."""
    template = "Extract all physical office locations (HQ, R&D, manufacturing) for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- Coordinates must be decimal degrees.\n- id must be slug: TICKER-CITY-TYPE.\n- confidence must be 'verified' (Tier 1 source), 'unverified', 'unknown', or explicitly set to null."
    sys_prompt = "Extract geographic office data. MANDATE: NEVER use placeholders like 'Office A'; only extract specific named sites."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['OFFICES', 'CORPORATE'], base_prompt, sys_prompt, OfficeList)
    res = await draft_section(_fill(base_prompt, facts=facts_text), OfficeList, sys_prompt)

    for o in res.offices:
        if (o.lat is None or o.lng is None) and o.country:
            c = geocoder.get_country_coords(o.country)
            if c: o.lat, o.lng, o.confidence = c["lat"], c["lng"], 'city_center_approximation'
    return res


async def get_supply_chain(facts: List, user_query: str) -> SupplyChainList:
    """Extract supply chain nodes from categorized facts."""
    template = "Extract supply chain partners, foundries, and manufacturing nodes for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- Identify 'critical' (single-source) vs 'standard' nodes.\n- Include coordinates (decimal degrees) for all nodes."
    sys_prompt = "Map supply chain infrastructure. MANDATE: NEVER use placeholders like 'Supplier 1'; only extract specific named partners."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['SUPPLY_CHAIN'], base_prompt, sys_prompt, SupplyChainList)
    res = await draft_section(_fill(base_prompt, facts=facts_text), SupplyChainList, sys_prompt)

    for n in res.supply_chain:
        if (n.lat is None or n.lng is None) and n.country:
            c = geocoder.get_country_coords(n.country)
            if c: n.lat, n.lng = c["lat"], c["lng"]
    return res


async def get_risks_signals(facts: List, user_query: str) -> RisksAndSignals:
    """Extract risks, customers, and expansion/contraction signals."""
    template = "Extract risks, customers, and signals for __QUERY__:\n__FACTS__\n\nRequirements:\n- riskScore: 1-5.\n- expansionSignals: include investment amount if available."
    sys_prompt = "Extract risks and customers. MANDATE: NEVER use placeholders like 'Customer A'; only extract specific named entities."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['RISKS', 'SIGNALS', 'CUSTOMERS'], base_prompt, sys_prompt, RisksAndSignals)
    res = await draft_section(_fill(base_prompt, facts=facts_text), RisksAndSignals, sys_prompt)

    for r in res.geopoliticalRisks:
        if (r.lat is None or r.lng is None) and r.region:
            c = geocoder.get_country_coords(r.region)
            if c: r.lat, r.lng = c["lat"], c["lng"]
    for e in res.expansionSignals:
        if (e.lat is None or e.lng is None) and e.location:
            c = geocoder.get_country_coords(e.location)
            if c: e.lat, e.lng = c["lat"], c["lng"]
    for cn in res.contractionSignals:
        if (cn.lat is None or cn.lng is None) and cn.location:
            c = geocoder.get_country_coords(cn.location)
            if c: cn.lat, cn.lng = c["lat"], c["lng"]
    for cust in res.customerConcentration:
        if (cust.lat is None or cust.lng is None) and cust.hqCountry:
            c = geocoder.get_country_coords(cust.hqCountry)
            if c: cust.lat, cust.lng = c["lat"], c["lng"]
    return res


# -----------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------

async def run_drafter(state: ResearchState) -> AsyncGenerator[Union[dict, ResearchState], None]:
    """
    Parallel multi-stage drafting with Granular Progress.
    Yields progress per drafted section and finally the updated state.
    """
    if not state.extracted_facts:
        logger.warning("No facts available to draft report.")
        yield state
        return

    logger.info(f"Drafting final reports in parallel.")
    
    try:
        # A. JSON Definitions (Basic, Anchor, Offices, Revenue, Supply, Risks)
        class BasicInfo(BaseModel):
            model_config = STRICT_CONFIG
            reasoning: str = Field(..., description="Logic for identifying core company identity.")
            company: str
            ticker: str | None
            website: str | None
            sector: str | None
            description: str
            generatedDate: str

        # A. Basic Info
        async def get_basic() -> BasicInfo:
            template = "Extract basic company details for __QUERY__ from these facts:\n__FACTS__\n\nRequirement: description must emphasize global geographic footprint. generatedDate must be YYYY-MM-DD."
            sys_prompt = "You are a precision Geo-Intelligence data extractor."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE', 'REVENUE'], base_prompt, sys_prompt, BasicInfo)
            return await draft_section(_fill(base_prompt, facts=facts_text), BasicInfo, sys_prompt)

        # B. Anchor Filing
        async def get_anchor() -> AnchorFilingSchema:
            template = "Identify the primary source filing (e.g. 10-K) from these facts for __QUERY__:\n__FACTS__\n\nExtract: type (10-K/10-Q/8-K), date (YYYY-MM-DD), and fiscalPeriod (e.g. FY2025)."
            sys_prompt = "Extract anchor filing details with ISO dates."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE'], base_prompt, sys_prompt, AnchorFilingSchema)
            return await draft_section(_fill(base_prompt, facts=facts_text), AnchorFilingSchema, sys_prompt)

        # C. Revenue Geography
        async def get_revenue() -> RevenueGeographySchema:
            template = "Extract revenue breakdown by geography for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- totalRevenue must be a raw number (e.g. 63900000000, not '$63.9B').\n- percentage must be a decimal (0.00 to 1.00)."
            sys_prompt = "Extract revenue geography with raw numerical precision."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['REVENUE'], base_prompt, sys_prompt, RevenueGeographySchema)
            return await draft_section(_fill(base_prompt, facts=facts_text), RevenueGeographySchema, sys_prompt)

        # ------------------------------------------------------------------
        # 1. Start JSON Drafting: module-level functions receive explicit args
        # ------------------------------------------------------------------
        json_tasks = {
            "basic": get_basic(),
            "anchor": get_anchor(),
            "offices": get_offices(state.extracted_facts, state.user_query),
            "revenue": get_revenue(),
            "supply": get_supply_chain(state.extracted_facts, state.user_query),
            "risks": get_risks_signals(state.extracted_facts, state.user_query)
        }
        
        json_results = {}
        total_steps = 13 # 6 JSON + 7 MD sections
        completed = 0

        # Yield discovery pulse
        yield {
            "status": "drafting",
            "units_discovered": total_steps,
            "message": f"Drafting: Initializing {total_steps} intelligence synthesis modules."
        }

        for future in asyncio.as_completed(json_tasks.values()):
            # Find which task finished (not strictly necessary but good for messaging)
            res = await future
            completed += 1
            # We map results back by checking types or using a different wrapper
            if isinstance(res, BasicInfo): json_results["b"] = res
            elif isinstance(res, AnchorFilingSchema): json_results["anc"] = res
            elif isinstance(res, OfficeList): json_results["o"] = res
            elif isinstance(res, RevenueGeographySchema): json_results["rev"] = res
            elif isinstance(res, SupplyChainList): json_results["sc"] = res
            elif isinstance(res, RisksAndSignals): json_results["rs"] = res

            yield {
                "status": "drafting",
                "unit": "llm",
                "message": f"Drafting: Assembling structured intelligence"
            }

        b, anc, o, rev, sc, rs = json_results["b"], json_results["anc"], json_results["o"], json_results["rev"], json_results["sc"], json_results["rs"]

        final_json_obj = GeoIntelligenceSchema(
            company=b.company, ticker=b.ticker, website=b.website, sector=b.sector, description=b.description,
            generatedDate=b.generatedDate, anchorFiling=anc, offices=o.offices, revenueGeography=rev,
            supplyChain=sc.supply_chain, customerConcentration=rs.customerConcentration, geopoliticalRisks=rs.geopoliticalRisks,
            expansionSignals=rs.expansionSignals, contractionSignals=rs.contractionSignals
        )
        state.final_report_json = final_json_obj.model_dump()

        # 2. Start MD Drafting
        async def draft_md_section(title: str, json_data: any, instructions: str) -> str:
            prompt = f"Generate '{title}' section.\n\nDATA:\n{json.dumps(json_data, indent=2)}\n\nINSTRUCTIONS:\n{instructions}\n\nReturn markdown content."
            res = await llm.generate_structured(prompt, MarkdownSectionSchema, "You are a professional Geo-Intelligence Analyst.")
            return res.markdown_content

        md_task_definitions = [
            ("## 1. Geographic Profile Summary", {"company": b.company, "description": b.description}, "Summarize global positioning."),
            ("## 2. MODULE A: Corporate Footprint", {"offices": [off.model_dump() for off in o.offices]}, "Detail physical locations."),
            ("## 3. MODULE B: Revenue Geography", rev.model_dump(), "Analyze regional revenue."),
            ("## 4. MODULE C: Supply Chain Map", {"supply_chain": [s.model_dump() for s in sc.supply_chain]}, "Map key nodes."),
            ("## 5. MODULE D: Customer concentration", {"customers": [c.model_dump() for c in rs.customerConcentration]}, "Map revenue dependencies."),
            ("## 6. MODULE E: Regulatory Risk", {"risks": [rk.model_dump() for rk in rs.geopoliticalRisks]}, "Analyze risks."),
            ("## 7. MODULE F: Strategic Signals", {"expansion": [ex.model_dump() for ex in rs.expansionSignals], "contraction": [co.model_dump() for co in rs.contractionSignals]}, "Detail shifts.")
        ]
        
        md_tasks = [draft_md_section(*args) for args in md_task_definitions]
        md_sections = [""] * 7 # Maintain order
        
        # To maintain order but yield progress, we map futures
        indexed_tasks = {asyncio.ensure_future(task): i for i, task in enumerate(md_tasks)}
        
        for future in asyncio.as_completed(indexed_tasks.keys()):
            content = await future
            idx = indexed_tasks[future]
            md_sections[idx] = content
            completed += 1
            
            yield {
                "status": "drafting",
                "unit": "llm",
                "message": f"Drafting: Finalizing narrative sections"
            }

        state.final_report_md = "\n\n".join(md_sections)
        logger.info("Markdown report assembled.")

    except Exception as e:
        logger.error(f"Error in parallel drafting: {e}")
        state.final_report_json = {"error": str(e), "partial": True}
        
    yield state

