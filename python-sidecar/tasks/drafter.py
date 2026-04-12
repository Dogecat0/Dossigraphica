from schemas import (
    ResearchState, GeoIntelligenceSchema, OfficeSchema, SupplyChainNodeSchema, 
    CustomerNodeSchema, GeopoliticalRiskSchema, ExpansionSignalSchema, 
    ContractionSignalSchema, RevenueGeographySchema, AnchorFilingSchema,
    MarkdownSectionSchema
)
from llm import llm, LLAMA_CTX_PER_REQUEST, LLAMA_OUTPUT_RESERVATION
from utils.geocoder import geocoder
import logging
import json
import asyncio
from typing import List, Type, TypeVar
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

async def draft_section(prompt: str, response_model: Type[T], system_prompt: str) -> T:
    """Helper to draft a single section with retries."""
    return await llm.generate_structured(
        prompt=prompt,
        response_model=response_model,
        system_prompt=system_prompt
    )

async def get_fact_subset(facts: List[any], categories: List[str], prompt_template: str, system_prompt: str) -> str:
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
    
    # Calculate available token space for facts. 
    # Use __FACTS__ marker to avoid any brace-related KeyError.
    test_prompt = prompt_template.replace("__FACTS__", "")
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": test_prompt}]
    overhead = llm.estimate_tokens(messages)
    target_tokens = LLAMA_CTX_PER_REQUEST - overhead - LLAMA_OUTPUT_RESERVATION
    
    return await llm.summarize_to_fit(full_facts_text, target_tokens, system_prompt="You are a data compression specialist.")

async def run_drafter(state: ResearchState) -> ResearchState:
    """
    Parallel multi-stage drafting to populate the GeoIntelligenceSchema.
    Uses __MARKER__ replacement to keep templates clean and error-free.
    """
    if not state.extracted_facts:
        logger.warning("No facts available to draft report.")
        return state

    logger.info(f"Drafting final reports in parallel using {len(state.extracted_facts)} categorized facts.")
    
    try:
        # Define local helper for brace-free replacement
        def fill(template: str, query: str = None, facts: str = None) -> str:
            res = template
            if query: res = res.replace("__QUERY__", query)
            if facts: res = res.replace("__FACTS__", facts)
            return res

        # A. Basic Info
        class BasicInfo(BaseModel):
            reasoning: str = Field(..., description="Logic for identifying core company identity.")
            company: str
            ticker: str
            website: str
            sector: str
            description: str
            generatedDate: str 

        async def get_basic():
            template = "Extract basic company details for __QUERY__ from these facts:\n__FACTS__\n\nRequirement: description must emphasize global geographic footprint. generatedDate must be YYYY-MM-DD."
            sys_prompt = "You are a precision Geo-Intelligence data extractor."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE', 'REVENUE'], base_prompt, sys_prompt)
            return await draft_section(fill(base_prompt, facts=facts_text), BasicInfo, sys_prompt)

        # B. Anchor Filing
        async def get_anchor():
            template = "Identify the primary source filing (e.g. 10-K) from these facts for __QUERY__:\n__FACTS__\n\nExtract: type (10-K/10-Q/8-K), date (YYYY-MM-DD), and fiscalPeriod (e.g. FY2025)."
            sys_prompt = "Extract anchor filing details with ISO dates."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE'], base_prompt, sys_prompt)
            return await draft_section(fill(base_prompt, facts=facts_text), AnchorFilingSchema, sys_prompt)

        # C. Offices
        class OfficeList(BaseModel):
            reasoning: str = Field(..., description="Analysis of office distribution and site criticality.")
            offices: List[OfficeSchema]

        async def get_offices():
            # Brackets removed from LLM slug instruction for simplicity
            template = "Extract all physical office locations (HQ, R&D, manufacturing) for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- Coordinates must be decimal degrees.\n- id must be slug: TICKER-CITY-TYPE.\n- confidence must be 'verified' (Tier 1 source) or 'unverified'."
            sys_prompt = "Extract geographic office data for the globe application."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['OFFICES', 'CORPORATE'], base_prompt, sys_prompt)
            res = await draft_section(fill(base_prompt, facts=facts_text), OfficeList, sys_prompt)
            
            for o in res.offices:
                if (o.lat is None or o.lng is None) and o.country:
                    c = geocoder.get_country_coords(o.country)
                    if c: o.lat, o.lng, o.confidence = c["lat"], c["lng"], 'city_center_approximation'
            return res

        # D. Revenue Geography
        async def get_revenue():
            template = "Extract revenue breakdown by geography for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- totalRevenue must be a raw number (e.g. 63900000000, not '$63.9B').\n- percentage must be a decimal (0.00 to 1.00)."
            sys_prompt = "Extract revenue geography with raw numerical precision."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['REVENUE'], base_prompt, sys_prompt)
            return await draft_section(fill(base_prompt, facts=facts_text), RevenueGeographySchema, sys_prompt)

        # E. Supply Chain
        class SupplyChainList(BaseModel):
            reasoning: str = Field(..., description="Strategy for mapping dependencies and risk nodes.")
            supply_chain: List[SupplyChainNodeSchema]

        async def get_supply_chain():
            template = "Extract supply chain partners, foundries, and manufacturing nodes for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- Identify 'critical' (single-source) vs 'standard' nodes.\n- Include coordinates (decimal degrees) for all nodes."
            sys_prompt = "Map the global supply chain infrastructure."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['SUPPLY_CHAIN'], base_prompt, sys_prompt)
            res = await draft_section(fill(base_prompt, facts=facts_text), SupplyChainList, sys_prompt)
            
            for n in res.supply_chain:
                if (n.lat is None or n.lng is None) and n.country:
                    c = geocoder.get_country_coords(n.country)
                    if c: n.lat, n.lng = c["lat"], c["lng"]
            return res

        # F. Risks & Signals
        class RisksAndSignals(BaseModel):
            reasoning: str = Field(..., description="Evaluation of regional stability and strategic indicators.")
            geopoliticalRisks: List[GeopoliticalRiskSchema]
            expansionSignals: List[ExpansionSignalSchema]
            contractionSignals: List[ContractionSignalSchema]
            customerConcentration: List[CustomerNodeSchema]

        async def get_risks_signals():
            template = "Extract risks, customers, and signals for __QUERY__:\n__FACTS__\n\nRequirements:\n- riskScore: 1-5.\n- expansionSignals: include investment amount if available."
            sys_prompt = "Extract geopolitical risks and strategic geographic signals."
            
            base_prompt = fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['RISKS', 'SIGNALS', 'CUSTOMERS'], base_prompt, sys_prompt)
            res = await draft_section(fill(base_prompt, facts=facts_text), RisksAndSignals, sys_prompt)
            
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

        # Parallel Execution
        results = await asyncio.gather(get_basic(), get_anchor(), get_offices(), get_revenue(), get_supply_chain(), get_risks_signals())
        b, anc, o, rev, sc, rs = results

        final_json_obj = GeoIntelligenceSchema(
            company=b.company, ticker=b.ticker, website=b.website, sector=b.sector, description=b.description,
            generatedDate=b.generatedDate, anchorFiling=anc, offices=o.offices, revenueGeography=rev,
            supplyChain=sc.supply_chain, customerConcentration=rs.customerConcentration, geopoliticalRisks=rs.geopoliticalRisks,
            expansionSignals=rs.expansionSignals, contractionSignals=rs.contractionSignals
        )

        state.final_report_json = final_json_obj.model_dump()
        logger.info("Structured JSON report assembled.")

        # Markdown Brief Generation
        async def draft_md_section(title: str, json_data: any, instructions: str) -> str:
            prompt = f"Generate '{title}' section.\n\nDATA:\n{json.dumps(json_data, indent=2)}\n\nINSTRUCTIONS:\n{instructions}\n\nReturn markdown content."
            res = await llm.generate_structured(prompt, MarkdownSectionSchema, "You are a professional Geo-Intelligence Analyst.")
            return res.markdown_content

        md_tasks = [
            draft_md_section("## 1. Geographic Profile Summary", {"company": b.company, "description": b.description}, "Summarize global positioning."),
            draft_md_section("## 2. MODULE A: Corporate Footprint", {"offices": [off.model_dump() for off in o.offices]}, "Detail physical locations."),
            draft_md_section("## 3. MODULE B: Revenue Geography", rev.model_dump(), "Analyze regional revenue."),
            draft_md_section("## 4. MODULE C: Supply Chain Map", {"supply_chain": [s.model_dump() for s in sc.supply_chain]}, "Map key nodes."),
            draft_md_section("## 5. MODULE D: Customer concentration", {"customers": [c.model_dump() for c in rs.customerConcentration]}, "Map revenue dependencies."),
            draft_md_section("## 6. MODULE E: Regulatory Risk", {"risks": [rk.model_dump() for rk in rs.geopoliticalRisks]}, "Analyze risks."),
            draft_md_section("## 7. MODULE F: Strategic Signals", {"expansion": [ex.model_dump() for ex in rs.expansionSignals], "contraction": [co.model_dump() for co in rs.contractionSignals]}, "Detail shifts.")
        ]
        md_sections = await asyncio.gather(*md_tasks)
        state.final_report_md = "\n\n".join(md_sections)
        logger.info("Markdown report assembled.")

    except Exception as e:
        logger.error(f"Error in parallel drafting: {e}")
        state.final_report_json = {"error": str(e), "partial": True}
        
    return state
