import { z } from "zod";

export const PlannerOutputSchema = z.object({
  researchPlan: z.string(),
  searchQueries: z.array(z.string())
});

export const ReflectorOutputSchema = z.object({
  isComplete: z.boolean(),
  knowledgeGaps: z.array(z.string()),
  newSearchQueries: z.array(z.string())
});

export const FactExtractionSchema = z.object({
  facts: z.array(
    z.object({
      claim: z.string(),
      sourceUrl: z.string()
    })
  )
});

export const OfficeSchema = z.object({
  id: z.string(),
  name: z.string(),
  city: z.string(),
  state: z.string().nullish(),
  country: z.string(),
  address: z.string().nullish(),
  lat: z.number(),
  lng: z.number(),
  businessFocus: z.string(),
  size: z.string().nullish(),
  type: z.enum([
    'headquarters',
    'regional',
    'engineering',
    'satellite',
    'manufacturing',
    'data_center',
    'sales',
    'logistics'
  ]),
  established: z.string().nullish(),
  source: z.string().nullish(),
  confidence: z.enum(['verified', 'unverified', 'city_center_approximation']).nullish()
});

export const RevenueSegmentSchema = z.object({
  region: z.string(),
  revenue: z.number().nullish(),
  percentage: z.number().nullish(),
  yoyGrowth: z.number().nullish(),
  notes: z.string().nullish()
});

export const RevenueGeographySchema = z.object({
  fiscalYear: z.string(),
  totalRevenue: z.number().nullish(),
  currency: z.string(),
  segments: z.array(RevenueSegmentSchema),
  concentrationRisk: z.string().nullish(),
  source: z.string()
});

export const SupplyChainNodeSchema = z.object({
  entity: z.string(),
  role: z.enum([
    'foundry',
    'assembly_test',
    'raw_material',
    'logistics',
    'contract_manufacturer',
    'key_supplier',
    'cloud_infrastructure'
  ]),
  city: z.string(),
  country: z.string(),
  lat: z.number().nullish(),  // relaxed from number
  lng: z.number().nullish(),  // relaxed from number
  product: z.string(),
  criticality: z.enum(['critical', 'important', 'standard']),
  source: z.string()
});

export const CustomerNodeSchema = z.object({
  customer: z.string(),
  revenueShare: z.string(),
  hqCity: z.string(),
  hqCountry: z.string(),
  lat: z.number().nullish(),
  lng: z.number().nullish(),
  relationship: z.string(),
  source: z.string()
});

export const GeopoliticalRiskSchema = z.object({
  region: z.string(),
  lat: z.number().nullish(),
  lng: z.number().nullish(),
  riskScore: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4), z.literal(5)]),
  riskCategory: z.string(),
  riskLabel: z.string(),
  description: z.string(),
  // Support both cases for existing data
  impactLevel: z.enum(['minimal', 'low', 'moderate', 'high', 'critical', 'Minimal', 'Low', 'Moderate', 'High', 'Critical']),
  filingReference: z.string(),
  lastUpdated: z.string()
});

export const ExpansionSignalSchema = z.object({
  type: z.literal('expansion'),
  location: z.string(),
  lat: z.number().nullish(),
  lng: z.number().nullish(),
  description: z.string(),
  estimatedTimeline: z.string().nullish(),
  investment: z.string().nullish(),
  source: z.string(),
  dateAnnounced: z.string().nullish()
});

export const ContractionSignalSchema = z.object({
  type: z.literal('contraction'),
  location: z.string(),
  lat: z.number().nullish(),
  lng: z.number().nullish(),
  description: z.string(),
  source: z.string()
});

export const AnchorFilingSchema = z.object({
  type: z.string(),
  date: z.string(),
  fiscalPeriod: z.string()
});

export const GeoIntelligenceSchema = z.object({
  company: z.string(),
  ticker: z.string(),
  website: z.string(),
  sector: z.string(),
  description: z.string(),
  anchorFiling: AnchorFilingSchema,
  generatedDate: z.string(),
  offices: z.array(OfficeSchema),
  revenueGeography: RevenueGeographySchema,
  supplyChain: z.array(SupplyChainNodeSchema),
  customerConcentration: z.array(CustomerNodeSchema),
  geopoliticalRisks: z.array(GeopoliticalRiskSchema),
  expansionSignals: z.array(ExpansionSignalSchema).nullish(),
  contractionSignals: z.array(ContractionSignalSchema).nullish()
});
