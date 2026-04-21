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
    category: Literal['CORPORATE', 'OFFICES', 'REVENUE', 'SUPPLY_CHAIN', 'CUSTOMERS', 'RISKS', 'SIGNALS', 'UNKNOWN'] = Field(..., description="The intelligence module this fact belongs to.")

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
    enrichment_queries: List[str] = []
    blocked_domains: set[str] = Field(default_factory=set, description="Domains that returned HTTP 451 from Jina, skipped in subsequent extractions.")
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

class SingleTriageSchema(BaseModel):
    """Binary outcome schema for evaluating a single URL's authority."""
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Brief justification for the boolean decision.")
    is_authoritative: bool = Field(..., description="True if the source is high-signal, credible, and NOT SEO spam.")

class SynthesizerSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="High-level analysis of the document's utility and geographic density.")
    extracted_facts: List[FactSchema] = Field(..., description="Dense list of specific categorized facts, numbers, and findings. If none are found, return an empty list.")

# --- Geo-Intelligence Output Schemas (Mirroring TS types - STRICT) ---

class OfficeSchema(BaseModel):
    model_config = STRICT_CONFIG
    id: str = Field(..., description="Unique ID for the office.")
    name: str = Field(..., description="Descriptive name of the office.")
    city: str | None = Field(..., description="City location.")
    state: str | None = Field(..., description="State/Province.")
    country: str | None = Field(..., description="Country location.")
    address: str | None = Field(..., description="Full street address.")
    lat: float | None = Field(..., description="Latitude coordinate.")
    lng: float | None = Field(..., description="Longitude coordinate.")
    businessFocus: str = Field(..., description="Primary business activity at this site.")
    size: str | None = Field(..., description="Approximate headcount or square footage.")
    type: Literal['headquarters', 'regional', 'engineering', 'satellite', 'manufacturing', 'data_center', 'sales', 'logistics'] = Field(..., description="Office category.")
    established: str | None = Field(..., description="Year established.")
    sources: List[str] = Field(..., description="List of source URLs or filings. Empty list if none.")
    confidence: Literal['verified', 'unverified', 'city_center_approximation', 'unknown'] | None = Field(..., description="Data accuracy label.")

class RevenueSegmentSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Geographic or business segment name.")
    revenue: float | None = Field(..., description="Revenue in USD millions.")
    percentage: float | None = Field(..., description="Percentage of total revenue.")
    yoyGrowth: float | None = Field(..., description="Year-over-year growth percentage.")
    notes: str | None = Field(..., description="Contextual notes about this segment.")

class RevenueGeographySchema(BaseModel):
    model_config = STRICT_CONFIG
    fiscalYear: str = Field(..., description="Reporting year.")
    totalRevenue: float | None = Field(..., description="Total company revenue.")
    currency: str = Field(..., description="Reporting currency (e.g., USD).")
    segments: List[RevenueSegmentSchema] = Field(..., description="Breakdown by geography or division.")
    concentrationRisk: str | None = Field(..., description="Notes on dependency on specific regions.")
    sources: List[str] = Field(..., description="List of source filing references. Empty list if none.")

class SupplyChainNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    entity: str = Field(..., description="Name of the supplier or partner.")
    role: Literal['foundry', 'assembly_test', 'raw_material', 'logistics', 'contract_manufacturer', 'key_supplier', 'cloud_infrastructure'] = Field(..., description="Role in the supply chain.")
    city: str | None = Field(..., description="Location city.")
    country: str | None = Field(..., description="Location country.")
    lat: float | None = Field(..., description="Latitude.")
    lng: float | None = Field(..., description="Longitude.")
    product: str = Field(..., description="Specific product or service provided.")
    criticality: Literal['critical', 'important', 'standard'] = Field(..., description="Importance to the company.")
    sources: List[str] = Field(..., description="List of source URLs. Empty list if none.")

class CustomerNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    customer: str = Field(..., description="Major customer name.")
    revenueShare: str | None = Field(..., description="Estimated percentage of revenue.")
    hqCity: str | None = Field(..., description="HQ city.")
    hqCountry: str | None = Field(..., description="HQ country.")
    lat: float | None = Field(..., description="Lat.")
    lng: float | None = Field(..., description="Lng.")
    relationship: str = Field(..., description="Nature of relationship.")
    sources: List[str] = Field(..., description="List of source URLs. Empty list if none.")

class GeopoliticalRiskSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Affected region.")
    lat: float | None = Field(..., description="Lat.")
    lng: float | None = Field(..., description="Lng.")
    riskScore: Literal[1, 2, 3, 4, 5] = Field(..., description="1-5 severity score.")
    riskCategory: Literal[
        'trade_restriction', 'regulatory_compliance', 'tax_policy', 
        'geopolitical_conflict', 'currency_exposure', 'environmental_regulation', 
        'labor_regulation', 'data_privacy', 'sanctions', 'political_instability'
    ] = Field(..., description="Category of risk.")
    riskLabel: str = Field(..., description="Short title.")
    description: str = Field(..., description="Detailed impact analysis.")
    impactLevel: Literal['minimal', 'low', 'moderate', 'high', 'critical'] = Field(..., description="Business impact level.")
    filingReference: str | None = Field(..., description="SEC filing or official source.")
    lastUpdated: str | None = Field(..., description="Date of update.")

class ExpansionSignalSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: Literal['expansion'] = Field(..., description="Signal type.")
    location: str = Field(..., description="Location city/country.")
    lat: float | None = Field(..., description="Lat.")
    lng: float | None = Field(..., description="Lng.")
    description: str = Field(..., description="Details of the expansion.")
    estimatedTimeline: str | None = Field(..., description="Projected completion.")
    investment: str | None = Field(..., description="USD amount if known.")
    sources: List[str] = Field(..., description="List of source URLs. Empty list if none.")
    dateAnnounced: str | None = Field(..., description="Date of news.")

class ContractionSignalSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: Literal['contraction'] = Field(..., description="Signal type.")
    location: str = Field(..., description="Location.")
    lat: float | None = Field(..., description="Lat.")
    lng: float | None = Field(..., description="Lng.")
    description: str = Field(..., description="Details of closures or layoffs.")
    sources: List[str] = Field(..., description="List of source URLs. Empty list if none.")

class AnchorFilingSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: str | None = Field(..., description="Filing type (e.g., 10-K).")
    date: str | None = Field(..., description="Filing date.")
    fiscalPeriod: str | None = Field(..., description="Reporting period.")

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
    ticker: str | None = Field(..., description="Stock ticker.")
    website: str | None = Field(..., description="Official URL.")
    sector: str | None = Field(..., description="Industry sector.")
    description: str = Field(..., description="Business summary.")
    anchorFiling: AnchorFilingSchema = Field(..., description="Primary source filing.")
    generatedDate: str = Field(..., description="Current date.")
    offices: List[OfficeSchema] = Field(..., description="Corporate office locations headquarters regional engineering manufacturing sites addresses")
    revenueGeography: RevenueGeographySchema = Field(..., description="Revenue breakdown by geographic region segment percentage growth year-over-year")
    supplyChain: List[SupplyChainNodeSchema] = Field(..., description="Supply chain suppliers foundries assembly partners critical vendors logistics")
    customerConcentration: List[CustomerNodeSchema] = Field(..., description="Top customers revenue share buyer relationships major clients")
    geopoliticalRisks: List[GeopoliticalRiskSchema] = Field(..., description="Geopolitical risks export controls trade restrictions sanctions regulatory compliance")
    expansionSignals: List[ExpansionSignalSchema] = Field(..., description="Expansion signals new facilities investments hiring growth announcements")
    contractionSignals: List[ContractionSignalSchema] = Field(..., description="Contraction signals plant closures layoffs restructuring downsizing")
