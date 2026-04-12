from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Union

# --- Strict Config to enforce GBNF grammar generation ---
STRICT_CONFIG = ConfigDict(extra='forbid', strict=True)

# --- Research State ---

class FactSchema(BaseModel):
    """Schema for LLM extraction (no metadata)."""
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Brief logical justification for why this specific fact was extracted and its relevance.")
    content: str = Field(..., description="The factual statement or data point.")
    category: Literal['CORPORATE', 'OFFICES', 'REVENUE', 'SUPPLY_CHAIN', 'CUSTOMERS', 'RISKS', 'SIGNALS'] = Field(..., description="The intelligence module this fact belongs to.")

class InternalFact(FactSchema):
    """Internal state fact with programmatic metadata."""
    source_url: str | None = Field(None, description="The URL or filing the fact was extracted from.")

class ResearchState(BaseModel):
    user_query: str
    pipeline_step: str = "init"
    scratchpad: str = ""
    extracted_facts: List[InternalFact] = []
    urls: List[str] = []
    search_queries: List[str] = []
    search_results: List[dict] = []
    raw_content: List[dict] = []
    nudge_count: int = 0
    is_exhausted: bool = False
    is_complete: bool = False
    final_report_md: str = ""
    final_report_json: Optional[dict] = None

# --- Intelligence Tasks Schemas (Reasoning First, All Required) ---

class PlannerSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Step-by-step internal logic for the research plan.")
    search_queries: List[str] = Field(..., description="Array of precise search strings to explore all facets of the query.")

class ElicitationSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Logic behind the elicitation and identification of blind spots.")
    critique: str = Field(..., description="Analysis of missing angles in the current search plan.")
    additional_items: List[str] = Field(..., description="New queries to fill the identified gaps.")
    is_exhausted: bool = Field(..., description="True if no new angles can possibly be explored.")

class TriageSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Evaluation of source relevance and authority.")
    top_urls: List[str] = Field(..., description="List of the most useful URLs for the research.")

class SynthesizerSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="High-level analysis of the document's utility and geographic density.")
    extracted_facts: List[FactSchema] = Field(..., description="Dense list of specific categorized facts, numbers, and findings. If none are found, return an empty list.")


# --- Geo-Intelligence Output Schemas (Mirroring TS types - STRICT) ---

class OfficeSchema(BaseModel):
    model_config = STRICT_CONFIG
    id: str = Field(..., description="Unique ID for the office.")
    name: str = Field(..., description="Descriptive name of the office.")
    city: str | None = Field(None, description="City location.")
    state: str | None = Field(None, description="State/Province.")
    country: str | None = Field(None, description="Country location.")
    address: str | None = Field(None, description="Full street address.")
    lat: float | None = Field(None, description="Latitude coordinate.")
    lng: float | None = Field(None, description="Longitude coordinate.")
    businessFocus: str = Field(..., description="Primary business activity at this site.")
    size: str | None = Field(None, description="Approximate headcount or square footage.")
    type: Literal['headquarters', 'regional', 'engineering', 'satellite', 'manufacturing', 'data_center', 'sales', 'logistics'] = Field(..., description="Office category.")
    established: str | None = Field(None, description="Year established.")
    source: str | None = Field(None, description="URL or filing where this location was found.")
    confidence: Literal['verified', 'unverified', 'city_center_approximation'] | None = Field(None, description="Data accuracy label.")

class RevenueSegmentSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Geographic or business segment name.")
    revenue: float | None = Field(None, description="Revenue in USD millions.")
    percentage: float | None = Field(None, description="Percentage of total revenue.")
    yoyGrowth: float | None = Field(None, description="Year-over-year growth percentage.")
    notes: str | None = Field(None, description="Contextual notes about this segment.")

class RevenueGeographySchema(BaseModel):
    model_config = STRICT_CONFIG
    fiscalYear: str = Field(..., description="Reporting year.")
    totalRevenue: float | None = Field(None, description="Total company revenue.")
    currency: str = Field(..., description="Reporting currency (e.g., USD).")
    segments: List[RevenueSegmentSchema] = Field(..., description="Breakdown by geography or division.")
    concentrationRisk: str | None = Field(None, description="Notes on dependency on specific regions.")
    source: str = Field(..., description="Source filing reference.")

class SupplyChainNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    entity: str = Field(..., description="Name of the supplier or partner.")
    role: Literal['foundry', 'assembly_test', 'raw_material', 'logistics', 'contract_manufacturer', 'key_supplier', 'cloud_infrastructure'] = Field(..., description="Role in the supply chain.")
    city: str | None = Field(None, description="Location city.")
    country: str | None = Field(None, description="Location country.")
    lat: float | None = Field(None, description="Latitude.")
    lng: float | None = Field(None, description="Longitude.")
    product: str = Field(..., description="Specific product or service provided.")
    criticality: Literal['critical', 'important', 'standard'] = Field(..., description="Importance to the company.")
    source: str = Field(..., description="Source reference.")

class CustomerNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    customer: str = Field(..., description="Major customer name.")
    revenueShare: str | None = Field(None, description="Estimated percentage of revenue.")
    hqCity: str | None = Field(None, description="HQ city.")
    hqCountry: str | None = Field(None, description="HQ country.")
    lat: float | None = Field(None, description="Lat.")
    lng: float | None = Field(None, description="Lng.")
    relationship: str = Field(..., description="Nature of relationship.")
    source: str = Field(..., description="Source reference.")

class GeopoliticalRiskSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Affected region.")
    lat: float | None = Field(None, description="Lat.")
    lng: float | None = Field(None, description="Lng.")
    riskScore: Literal[1, 2, 3, 4, 5] = Field(..., description="1-5 severity score.")
    riskCategory: Literal[
        'trade_restriction', 'regulatory_compliance', 'tax_policy', 
        'geopolitical_conflict', 'currency_exposure', 'environmental_regulation', 
        'labor_regulation', 'data_privacy', 'sanctions', 'political_instability'
    ] = Field(..., description="Category of risk.")
    riskLabel: str = Field(..., description="Short title.")
    description: str = Field(..., description="Detailed impact analysis.")
    impactLevel: Literal['minimal', 'low', 'moderate', 'high', 'critical'] = Field(..., description="Business impact level.")
    filingReference: str = Field(..., description="SEC filing or official source.")
    lastUpdated: str = Field(..., description="Date of update.")

class ExpansionSignalSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: Literal['expansion'] = Field(..., description="Signal type.")
    location: str = Field(..., description="Location city/country.")
    lat: float | None = Field(None, description="Lat.")
    lng: float | None = Field(None, description="Lng.")
    description: str = Field(..., description="Details of the expansion.")
    estimatedTimeline: str | None = Field(None, description="Projected completion.")
    investment: str | None = Field(None, description="USD amount if known.")
    source: str = Field(..., description="Source reference.")
    dateAnnounced: str | None = Field(None, description="Date of news.")

class ContractionSignalSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: Literal['contraction'] = Field(..., description="Signal type.")
    location: str = Field(..., description="Location.")
    lat: float | None = Field(None, description="Lat.")
    lng: float | None = Field(None, description="Lng.")
    description: str = Field(..., description="Details of closures or layoffs.")
    source: str = Field(..., description="Source reference.")

class AnchorFilingSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: str = Field(..., description="Filing type (e.g., 10-K).")
    date: str = Field(..., description="Filing date.")
    fiscalPeriod: str = Field(..., description="Reporting period.")

class MarkdownSectionSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Plan for the markdown narrative structure.")
    markdown_content: str = Field(..., description="The full markdown content for the section, including headers and markdown formatting.")

class SummarySchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Logic for data compression and point selection.")
    summary: str = Field(..., description="A high-density summary of the provided information, preserving all exact numbers, coordinates, and citations.")

class GeoIntelligenceSchema(BaseModel):
    model_config = STRICT_CONFIG
    company: str = Field(..., description="Company name.")
    ticker: str = Field(..., description="Stock ticker.")
    website: str = Field(..., description="Official URL.")
    sector: str = Field(..., description="Industry sector.")
    description: str = Field(..., description="Business summary.")
    anchorFiling: AnchorFilingSchema = Field(..., description="Primary source filing.")
    generatedDate: str = Field(..., description="Current date.")
    offices: List[OfficeSchema] = Field(..., description="Global office locations.")
    revenueGeography: RevenueGeographySchema = Field(..., description="Revenue breakdown.")
    supplyChain: List[SupplyChainNodeSchema] = Field(..., description="Supply chain map.")
    customerConcentration: List[CustomerNodeSchema] = Field(..., description="Key customer map.")
    geopoliticalRisks: List[GeopoliticalRiskSchema] = Field(..., description="Regional risk map.")
    expansionSignals: List[ExpansionSignalSchema] = Field(..., description="Growth indicators.")
    contractionSignals: List[ContractionSignalSchema] = Field(..., description="Risk indicators.")

# --- Intelligence Goals (Reference for Planner, Elicitation & Preprocessor) ---

INTELLIGENCE_GOALS = """
Your goal is to populate a forensic Geo-Intelligence Brief. You must target the following modules:

1. CORPORATE FOOTPRINT:
   - Identify all physical office locations (HQ, Regional, Engineering, Manufacturing, Data Centers).
   - For each office, find: City, Country, Business Focus (e.g. R&D), Type, and Year Established.
   - Seek primary source evidence for coordinates (lat/lng).

2. REVENUE GEOGRAPHY:
   - Find the exact revenue breakdown by region (e.g. Taiwan, China, USA, Korea, Netherlands).
   - Extract Total Revenue, Currency, and YoY growth percentages for each segment.
   - Identify 'Concentration Risk' - heavy dependency on specific jurisdictional revenues.

3. SUPPLY CHAIN MAP:
   - Identify critical foundries, assembly/test sites, and raw material suppliers.
   - Map their physical locations (City/Country) and their role (e.g. key supplier, logistics hub).
   - Determine 'Criticality' (critical/important/standard) to the company's operations.

4. CUSTOMER CONCENTRATION:
   - Identify major customers (e.g. Intel, TSMC, Samsung) and their revenue share.
   - Find customer HQ locations to map the geographic flow of products.

5. GEOPOLITICAL RISKS:
   - Identify specific risks: export controls, trade restrictions, regulatory probes, sanctions, or tax policies.
   - Categorize by region and assign a 1-5 severity score based on business impact.

6. STRATEGIC SIGNALS:
   - Expansion: New plant openings, major R&D investments, or headcount growth in specific regions.
   - Contraction: Plant closures, layoffs, or regional exits.
"""
