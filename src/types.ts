/** Office type categories */
export type OfficeType =
    | 'headquarters'
    | 'regional'
    | 'engineering'
    | 'satellite'
    | 'manufacturing'
    | 'data_center'
    | 'sales'
    | 'logistics'

/** A single office location */
export interface Office {
    id: string
    name: string
    city: string
    state?: string | null
    country: string
    address?: string | null
    lat: number
    lng: number
    businessFocus: string
    type: OfficeType
    source?: string | null
    confidence?: 'verified' | 'unverified' | 'city_center_approximation' | null
    /** Set at runtime when flattening — the parent company name */
    companyId?: string
}

/** A company with its office locations */
export interface Company {
    company: string
    website: string
    ticker: string
    sector: string
    description: string
    offices: Office[]
}

/** Ring datum used by react-globe.gl rings layer */
export interface RingDatum {
    lat: number
    lng: number
    color: string
    size: number
    isSelected: boolean
    isCore: boolean
    officeRef: Office
}

/** Arc datum used by react-globe.gl arcs layer */
export interface ArcDatum {
    startLat: number
    startLng: number
    endLat: number
    endLng: number
    color: [string, string]
}

/* ===== Geo-Intelligence Types ===== */

export interface RevenueSegment {
    region: string
    revenue: number | null
    percentage: number | null
    yoyGrowth: number | null
    notes: string | null
}

export interface RevenueGeography {
    fiscalYear: string
    totalRevenue: number | null
    currency: string
    segments: RevenueSegment[]
    concentrationRisk: string | null
    source: string
}

export interface SupplyChainNode {
    entity: string
    role: 'foundry' | 'assembly_test' | 'raw_material' | 'logistics' | 'contract_manufacturer' | 'key_supplier' | 'cloud_infrastructure'
    city: string
    country: string
    lat: number | null
    lng: number | null
    product: string
    criticality: 'critical' | 'important' | 'standard'
    source: string
}

export interface CustomerNode {
    customer: string
    revenueShare: string | null
    hqCity: string | null
    hqCountry: string | null
    lat: number | null
    lng: number | null
    relationship: string
    source: string
}

export interface GeopoliticalRisk {
    region: string
    lat: number | null
    lng: number | null
    riskScore: 1 | 2 | 3 | 4 | 5
    riskCategory: string
    riskLabel: string
    description: string
    impactLevel: 'minimal' | 'low' | 'moderate' | 'high' | 'critical'
    filingReference: string
    lastUpdated: string
}

export interface AnchorFiling {
    type: string
    date: string
    fiscalPeriod: string
}

/** Root geo-intelligence data for a company */
export interface GeoIntelligence {
    company: string
    ticker: string
    website: string
    sector: string
    description: string
    anchorFiling: AnchorFiling
    generatedDate: string
    offices: Office[]
    revenueGeography: RevenueGeography
    supplyChain: SupplyChainNode[]
    customerConcentration: CustomerNode[]
    geopoliticalRisks: GeopoliticalRisk[]
}

/* ===== Cross-Company Analysis Types ===== */

export interface DependencyLink {
    from: string // Ticker
    to: string // Ticker or Entity Name
    type: 'buyer_supplier' | 'shared_dependency' | 'competitor' | 'equipment_provider'
    description: string
    strength?: 'critical' | 'important' | 'standard'
    value?: string // e.g., "22% of revenue"
}

export interface ChainMatrix {
    lastUpdated: string
    version: string
    dependencies: DependencyLink[]
}

export interface RegionalRiskScore {
    region: string
    lat: number
    lng: number
    overallScore: number // 1-10
    contributingCompanies: {
        ticker: string
        riskScore: number
        impactLevel: string
        category: string
    }[]
    riskDimensions: string[]
    summary: string
}

export interface RiskConvergence {
    lastUpdated: string
    regions: RegionalRiskScore[]
}

export interface Chokepoint {
    id: string
    name: string
    type: string
    location: string
    lat: number
    lng: number
    severity: 'critical' | 'high' | 'medium' | 'low'
    description: string
    exposedCompanies: string[] // Tickers
    mitigationStatus: string
}

export interface ChokepointAnalysis {
    lastUpdated: string
    chokepoints: Chokepoint[]
}

export type MapEntity =
    | { type: 'office', data: Office }
    | { type: 'risk', data: GeopoliticalRisk }
    | { type: 'regionalRisk', data: RegionalRiskScore }
    | { type: 'chokepoint', data: Chokepoint }
    | { type: 'supplier', data: SupplyChainNode }
    | { type: 'customer', data: CustomerNode }

/** Layer visibility toggles */
export type LayerName = 'offices' | 'supplyChain' | 'customers' | 'risks' | 'chain' | 'chokepoints'
