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
    state?: string
    country: string
    address?: string
    lat: number
    lng: number
    businessFocus: string
    size?: string
    type: OfficeType
    established?: string
    source?: string
    confidence?: 'verified' | 'unverified' | 'city_center_approximation'
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
    percentage: number
    yoyGrowth: number | null
    notes: string
}

export interface RevenueGeography {
    fiscalYear: string
    totalRevenue: number
    currency: string
    segments: RevenueSegment[]
    concentrationRisk: string
    source: string
}

export interface SupplyChainNode {
    entity: string
    role: 'foundry' | 'assembly_test' | 'raw_material' | 'logistics' | 'contract_manufacturer' | 'key_supplier' | 'cloud_infrastructure'
    city: string
    country: string
    lat: number
    lng: number
    product: string
    criticality: 'critical' | 'important' | 'standard'
    source: string
}

export interface CustomerNode {
    customer: string
    revenueShare: string
    hqCity: string
    hqCountry: string
    lat: number
    lng: number
    relationship: string
    source: string
}

export interface GeopoliticalRisk {
    region: string
    lat: number
    lng: number
    riskScore: 1 | 2 | 3 | 4 | 5
    riskCategory: string
    riskLabel: string
    description: string
    impactLevel: 'minimal' | 'low' | 'moderate' | 'high' | 'critical'
    filingReference: string
    lastUpdated: string
}

export interface ExpansionSignal {
    type: 'expansion'
    location: string
    lat?: number
    lng?: number
    description: string
    estimatedTimeline?: string
    investment?: string
    source: string
    dateAnnounced?: string
}

export interface ContractionSignal {
    type: 'contraction'
    location: string
    lat?: number
    lng?: number
    description: string
    source: string
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
    expansionSignals: ExpansionSignal[]
    contractionSignals: ContractionSignal[]
}

/** Layer visibility toggles */
export type LayerName = 'offices' | 'supplyChain' | 'customers' | 'risks'
