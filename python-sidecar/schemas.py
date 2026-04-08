from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Union

# --- Strict Config to enforce GBNF grammar generation ---
STRICT_CONFIG = ConfigDict(extra='forbid', strict=True)

# --- Research State ---

class ResearchState(BaseModel):
    user_query: str
    scratchpad: str = ""
    extracted_facts: List[str] = []
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
    search_queries: List[str] = Field(..., description="Array of 3 to 5 precise search strings.")

class ElicitationSchema(BaseModel):
    model_config = STRICT_CONFIG
    critique: str = Field(..., description="Analysis of missing angles in the current search plan.")
    additional_items: List[str] = Field(..., description="New queries to fill the identified gaps.")
    is_exhausted: bool = Field(..., description="True if no new angles can possibly be explored.")

class TriageSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(..., description="Evaluation of source relevance and authority.")
    top_urls: List[str] = Field(..., description="List of the top 5 most useful URLs for the research.")

class SynthesizerSchema(BaseModel):
    model_config = STRICT_CONFIG
    is_useful: bool = Field(..., description="Whether the document contains facts relevant to the query.")
    extracted_facts: List[str] = Field(..., description="Dense list of specific facts, numbers, and findings.")

class ReflectorSchema(BaseModel):
    model_config = STRICT_CONFIG
    is_complete: bool = Field(..., description="Whether the original query is fully answered.")
    reasoning: str = Field(..., description="Audit of the current facts against the research goal.")
    gaps: List[str] = Field(..., description="Factual information still missing from the scratchpad.")
    new_queries: List[str] = Field(..., description="Queries designed specifically to close the data gaps.")

# --- Geo-Intelligence Output Schemas (Mirroring TS types - STRICT) ---

class OfficeSchema(BaseModel):
    model_config = STRICT_CONFIG
    id: str = Field(..., description="Unique ID for the office.")
    name: str = Field(..., description="Descriptive name of the office.")
    city: str = Field(..., description="City location.")
    state: Optional[str] = Field(None, description="State/Province.")
    country: str = Field(..., description="Country location.")
    address: Optional[str] = Field(None, description="Full street address.")
    lat: float = Field(..., description="Latitude coordinate.")
    lng: float = Field(..., description="Longitude coordinate.")
    businessFocus: str = Field(..., description="Primary business activity at this site.")
    size: Optional[str] = Field(None, description="Approximate headcount or square footage.")
    type: Literal['headquarters', 'regional', 'engineering', 'satellite', 'manufacturing', 'data_center', 'sales', 'logistics'] = Field(..., description="Office category.")
    established: Optional[str] = Field(None, description="Year established.")
    source: Optional[str] = Field(None, description="URL or filing where this location was found.")
    confidence: Optional[Literal['verified', 'unverified', 'city_center_approximation']] = Field(None, description="Data accuracy label.")

class RevenueSegmentSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Geographic or business segment name.")
    revenue: Optional[float] = Field(None, description="Revenue in USD millions.")
    percentage: Optional[float] = Field(None, description="Percentage of total revenue.")
    yoyGrowth: Optional[float] = Field(None, description="Year-over-year growth percentage.")
    notes: Optional[str] = Field(None, description="Contextual notes about this segment.")

class RevenueGeographySchema(BaseModel):
    model_config = STRICT_CONFIG
    fiscalYear: str = Field(..., description="Reporting year.")
    totalRevenue: Optional[float] = Field(None, description="Total company revenue.")
    currency: str = Field(..., description="Reporting currency (e.g., USD).")
    segments: List[RevenueSegmentSchema] = Field(..., description="Breakdown by geography or division.")
    concentrationRisk: Optional[str] = Field(None, description="Notes on dependency on specific regions.")
    source: str = Field(..., description="Source filing reference.")

class SupplyChainNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    entity: str = Field(..., description="Name of the supplier or partner.")
    role: Literal['foundry', 'assembly_test', 'raw_material', 'logistics', 'contract_manufacturer', 'key_supplier', 'cloud_infrastructure'] = Field(..., description="Role in the supply chain.")
    city: str = Field(..., description="Location city.")
    country: str = Field(..., description="Location country.")
    lat: Optional[float] = Field(None, description="Latitude.")
    lng: Optional[float] = Field(None, description="Longitude.")
    product: str = Field(..., description="Specific product or service provided.")
    criticality: Literal['critical', 'important', 'standard'] = Field(..., description="Importance to the company.")
    source: str = Field(..., description="Source reference.")

class CustomerNodeSchema(BaseModel):
    model_config = STRICT_CONFIG
    customer: str = Field(..., description="Major customer name.")
    revenueShare: str = Field(..., description="Estimated percentage of revenue.")
    hqCity: str = Field(..., description="HQ city.")
    hqCountry: str = Field(..., description="HQ country.")
    lat: Optional[float] = Field(None, description="Lat.")
    lng: Optional[float] = Field(None, description="Lng.")
    relationship: str = Field(..., description="Nature of relationship.")
    source: str = Field(..., description="Source reference.")

class GeopoliticalRiskSchema(BaseModel):
    model_config = STRICT_CONFIG
    region: str = Field(..., description="Affected region.")
    lat: Optional[float] = Field(None, description="Lat.")
    lng: Optional[float] = Field(None, description="Lng.")
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
    lat: Optional[float] = Field(None, description="Lat.")
    lng: Optional[float] = Field(None, description="Lng.")
    description: str = Field(..., description="Details of the expansion.")
    estimatedTimeline: Optional[str] = Field(None, description="Projected completion.")
    investment: Optional[str] = Field(None, description="USD amount if known.")
    source: str = Field(..., description="Source reference.")
    dateAnnounced: Optional[str] = Field(None, description="Date of news.")

class ContractionSignalSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: Literal['contraction'] = Field(..., description="Signal type.")
    location: str = Field(..., description="Location.")
    lat: Optional[float] = Field(None, description="Lat.")
    lng: Optional[float] = Field(None, description="Lng.")
    description: str = Field(..., description="Details of closures or layoffs.")
    source: str = Field(..., description="Source reference.")

class AnchorFilingSchema(BaseModel):
    model_config = STRICT_CONFIG
    type: str = Field(..., description="Filing type (e.g., 10-K).")
    date: str = Field(..., description="Filing date.")
    fiscalPeriod: str = Field(..., description="Reporting period.")

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
