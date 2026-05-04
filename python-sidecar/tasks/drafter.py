from schemas import (
    ResearchState, GeoIntelligenceSchema, OfficeSchema, SupplyChainNodeSchema, 
    CustomerNodeSchema, GeopoliticalRiskSchema, 
    RevenueGeographySchema, AnchorFilingSchema,
    MarkdownSectionSchema, STRICT_CONFIG, InternalFact
)
from llm import llm, LLAMA_CTX_PER_REQUEST, LLAMA_OUTPUT_RESERVATION
from utils.geocoder import geocoder
import logging
import json
import asyncio
from datetime import datetime
from typing import List, Type, TypeVar, AsyncGenerator, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# --- Shared wrapper types for structured LLM output ---

class OfficeList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Analysis of office distribution and site criticality.")
    offices: List[OfficeSchema]

class SupplyChainList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Strategy for mapping dependencies and risk nodes.")
    supply_chain: List[SupplyChainNodeSchema]

class RiskList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Evaluation of regional stability and regulatory trends.")
    geopoliticalRisks: List[GeopoliticalRiskSchema]

class CustomerList(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Evaluation of revenue dependency and major buyer relationships.")
    customerConcentration: List[CustomerNodeSchema]

async def draft_section(prompt: str, response_model: Type[T], system_prompt: str, facts: str = None) -> T:
    """Helper to draft a single section with retries."""
    return await llm.generate_structured(
        prompt=prompt,
        response_model=response_model,
        system_prompt=system_prompt,
        facts=facts
    )

async def get_fact_subset(facts: List[InternalFact], categories: List[str]) -> str:
    """
    Filters facts by category and returns a grouped formatted string. 
    """
    output = []
    for cat in categories:
        filtered = [f for f in facts if f.category == cat]
        if not filtered: continue
        output.append(f"### {cat}:\n")
        output.extend([f"- {fact.content} (Source: {fact.source_url})\n" for fact in filtered])
            
    return "".join(output) if output else ""
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
    sys_prompt = f"Extract geographic office data for {user_query}. MANDATE: Prioritize the parent company's primary footprint. Include major subsidiaries only if they are globally significant. NEVER use placeholders like 'Office A'; only extract specific named sites."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['OFFICES', 'CORPORATE'])
    res = await draft_section(base_prompt, OfficeList, sys_prompt, facts=facts_text)

    for o in res.offices:
        if (o.lat is None or o.lng is None) and (o.city or o.country):
            location_str = f"{o.city}, {o.country}" if o.city and o.country else (o.city or o.country)
            c = await geocoder.get_coords_async(city=o.city, country=o.country)
            if c:
                o.lat, o.lng = c["lat"], c["lng"]
                if "confidence" in c:
                    o.confidence = c["confidence"]
                elif o.confidence is None:
                    o.confidence = 'city_center_approximation'
    return res


async def get_supply_chain(facts: List, user_query: str) -> SupplyChainList:
    """Extract supply chain partners, foundries, and manufacturing nodes for __QUERY__ from these facts."""
    template = "Extract supply chain partners, foundries, and manufacturing nodes for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- Identify 'critical' (single-source) vs 'standard' nodes.\n- Include coordinates (decimal degrees) for all nodes."
    sys_prompt = f"Map supply chain infrastructure for {user_query}. MANDATE: Prioritize direct suppliers to the parent company. Include subsidiary-specific suppliers only if they are critical to the broader group. NEVER use placeholders like 'Supplier 1'; only extract specific named partners."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['SUPPLY_CHAIN'])
    res = await draft_section(base_prompt, SupplyChainList, sys_prompt, facts=facts_text)

    for n in res.supply_chain:
        if (n.lat is None or n.lng is None) and (n.city or n.country):
            location_str = f"{n.city}, {n.country}" if n.city and n.country else (n.city or n.country)
            c = await geocoder.get_coords_async(city=n.city, country=n.country)
            if c:
                n.lat, n.lng = c["lat"], c["lng"]
    return res


async def get_geopolitical_risks(facts: List, user_query: str) -> RiskList:
    """Extract and geocode geopolitical risks."""
    template = "Extract geopolitical risks for __QUERY__:\n__FACTS__\n\nRequirements:\n- riskScore: 1-5.\n- region: Identify the specific region (priorityize), country, or city affected."
    sys_prompt = f"Extract risks for {user_query}. MANDATE: Focus on risks affecting the parent entity and its primary revenue streams. NEVER use placeholders; only extract specific named entities and regions/countries."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['RISKS'])
    res = await draft_section(base_prompt, RiskList, sys_prompt, facts=facts_text)

    for r in res.geopoliticalRisks:
        if (r.lat is None or r.lng is None) and r.region:
            c = await geocoder.get_coords_async(location_string=r.region)
            if c: r.lat, r.lng = c["lat"], c["lng"]
    return res


async def get_customer_concentration(facts: List, user_query: str) -> CustomerList:
    """Extract and geocode customer concentration."""
    template = "Extract major customers and revenue dependencies for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- revenueShare: Extract the exact percentage or dollar amount of revenue dependency if mentioned.\n- Provide HQ city/country details to enable accurate geocoding."
    sys_prompt = "Extract customers. MANDATE: NEVER use placeholders; only extract specific named buyers and their financial share if available."

    base_prompt = _fill(template, query=user_query)
    facts_text = await get_fact_subset(facts, ['CUSTOMERS'])
    res = await draft_section(base_prompt, CustomerList, sys_prompt, facts=facts_text)

    for cust in res.customerConcentration:
        if (cust.lat is None or cust.lng is None) and (cust.hqCity or cust.hqCountry):
            location_str = f"{cust.hqCity}, {cust.hqCountry}" if cust.hqCity and cust.hqCountry else (cust.hqCity or cust.hqCountry)
            c = await geocoder.get_coords_async(city=cust.hqCity, country=cust.hqCountry)
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

    logger.debug(f"Drafting final reports in parallel.")
    
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

        # A. Basic Info
        async def get_basic() -> BasicInfo:
            template = "Extract basic company details for __QUERY__ from these facts:\n__FACTS__\n\nRequirement: description must emphasize global geographic footprint."
            sys_prompt = "You are a precision Geo-Intelligence data extractor."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE', 'REVENUE'])
            return await draft_section(base_prompt, BasicInfo, sys_prompt, facts=facts_text)

        # B. Anchor Filing
        async def get_anchor() -> AnchorFilingSchema:
            template = "Identify the primary source filing (e.g. 10-K) from these facts for __QUERY__:\n__FACTS__\n\nExtract: type (10-K/10-Q/8-K), date (YYYY-MM-DD), and fiscalPeriod."
            sys_prompt = "Extract anchor filing details with ISO dates."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['CORPORATE'])
            return await draft_section(base_prompt, AnchorFilingSchema, sys_prompt, facts=facts_text)

        # C. Revenue Geography
        async def get_revenue() -> RevenueGeographySchema:
            template = "Extract revenue breakdown by geography for __QUERY__ from these facts:\n__FACTS__\n\nRequirements:\n- totalRevenue must be a raw number (e.g. 63900000000, not '$63.9B').\n- percentage must be a decimal (0.00 to 1.00)."
            sys_prompt = "Extract revenue geography with raw numerical precision."
            base_prompt = _fill(template, query=state.user_query)
            facts_text = await get_fact_subset(state.extracted_facts, ['REVENUE'])
            return await draft_section(base_prompt, RevenueGeographySchema, sys_prompt, facts=facts_text)

        # ------------------------------------------------------------------
        # 1. Start JSON Drafting: module-level functions receive explicit args
        # ------------------------------------------------------------------
        total_steps = 13  # 7 JSON + 6 MD sections

        # Yield discovery pulse
        yield {
            "status": "drafting",
            "units_discovered": total_steps,
            "message": f"Drafting: Initializing {total_steps} intelligence synthesis modules."
        }

        # ------------------------------------------------------------------
        # Phase 1: JSON Drafting (6 parallel tasks)
        #
        # asyncio.as_completed() yields *new* wrapper coroutines, so the
        # original future objects cannot be used as dict keys for back-
        # mapping results. Instead, we wrap each task to push (key, result)
        # pairs through a queue, preserving both identity and progress.
        # ------------------------------------------------------------------
        json_progress_queue: asyncio.Queue = asyncio.Queue()

        async def _json_task(key: str, coro):
            result = await coro
            await json_progress_queue.put((key, result))

        json_coros = [
            _json_task("b",   get_basic()),
            _json_task("anc", get_anchor()),
            _json_task("o",   get_offices(state.extracted_facts, state.user_query)),
            _json_task("rev", get_revenue()),
            _json_task("sc",  get_supply_chain(state.extracted_facts, state.user_query)),
            _json_task("risk", get_geopolitical_risks(state.extracted_facts, state.user_query)),
            _json_task("cust", get_customer_concentration(state.extracted_facts, state.user_query)),
        ]

        gather_task = asyncio.ensure_future(asyncio.gather(*json_coros))

        json_results = {}
        for _ in range(len(json_coros)):
            key, result = await json_progress_queue.get()
            json_results[key] = result
            yield {
                "status": "drafting",
                "message": "Drafting: Assembling structured intelligence"
            }

        await gather_task  # propagate any exceptions

        b, anc, o, rev, sc, risk, cust = (
            json_results["b"], json_results["anc"], json_results["o"],
            json_results["rev"], json_results["sc"], json_results["risk"],
            json_results["cust"]
        )

        final_json_obj = GeoIntelligenceSchema(
            company=b.company, ticker=b.ticker, website=b.website, sector=b.sector, description=b.description,
            generatedDate=datetime.now().strftime("%Y-%m-%d"), anchorFiling=anc, offices=o.offices, revenueGeography=rev,
            supplyChain=sc.supply_chain, customerConcentration=cust.customerConcentration, geopoliticalRisks=risk.geopoliticalRisks
        )
        state.final_report_json = final_json_obj.model_dump()

        # ------------------------------------------------------------------
        # Phase 2: MD Drafting (7 parallel tasks, order-preserving)
        # ------------------------------------------------------------------
        async def draft_md_section(title: str, json_data: any, instructions: str) -> str:
            prompt = f"Generate '{title}' section.\n\nDATA:\n{json.dumps(json_data, indent=2)}\n\nINSTRUCTIONS:\n{instructions}\n\nReturn markdown content."
            res = await llm.generate_structured(prompt, MarkdownSectionSchema, "You are a professional Geo-Intelligence Analyst.")
            return res.markdown_content

        md_task_definitions = [
            ("## 1. Geographic Profile Summary", {"company": b.company, "description": b.description}, "Summarize global positioning."),
            ("## 2. Corporate Footprint", {"offices": [off.model_dump() for off in o.offices]}, "Detail physical locations."),
            ("## 3. Revenue Geography", rev.model_dump(), "Analyze regional revenue."),
            ("## 4. Supply Chain Map", {"supply_chain": [s.model_dump() for s in sc.supply_chain]}, "Map key nodes."),
            ("## 5. Customer Concentration", {"customers": [c.model_dump() for c in cust.customerConcentration]}, "Map revenue dependencies."),
            ("## 6. Regulatory Risk", {"risks": [rk.model_dump() for rk in risk.geopoliticalRisks]}, "Analyze risks.")
        ]

        md_progress_queue: asyncio.Queue = asyncio.Queue()
        md_sections = [""] * len(md_task_definitions)

        async def _md_task(index: int, title: str, json_data, instructions: str):
            content = await draft_md_section(title, json_data, instructions)
            await md_progress_queue.put((index, content))

        md_coros = [_md_task(i, *args) for i, args in enumerate(md_task_definitions)]
        md_gather = asyncio.ensure_future(asyncio.gather(*md_coros))

        for _ in range(len(md_coros)):
            idx, content = await md_progress_queue.get()
            md_sections[idx] = content
            yield {
                "status": "drafting",
                "message": "Drafting: Finalizing narrative sections"
            }

        await md_gather  # propagate any exceptions

        state.final_report_md = "\n\n".join(md_sections)
        logger.debug("Markdown report assembled.")

    except Exception as e:
        logger.error(f"Error in parallel drafting: {e}")
        state.final_report_json = {"error": str(e), "partial": True}
        
    yield state
