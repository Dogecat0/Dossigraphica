### **The "Geo-Intelligence Analyst" Extraction Prompt — Output Format (V1)**

**Role:** Act as a Senior Geopolitical Risk & Corporate Intelligence Analyst at a top-tier institutional firm. **Your client** is a Portfolio Manager who requires a **Geographic Intelligence Brief** for \[INSERT TICKER/COMPANY NAME\]. **Mission:** Conduct a forensic extraction of all geographically relevant data from the company's most recent SEC filings, earnings transcripts, press releases, and corporate disclosures. Map the company's global footprint, revenue geography, supply chain dependencies, customer concentration, regulatory exposure, and strategic expansion signals. **Output:** Please output the report in **two formats**: (1) a structured JSON block and (2) a narrative Markdown geographic intelligence brief. Both outputs must be included in every report.

---

**PART 0: Ticker & Input Protocol**

The user specifies \[TICKER/COMPANY NAME\]. You independently locate all relevant SEC filings, earnings transcripts, press releases, and corporate disclosures to produce the Geo-Intelligence Brief.

---

**PART 1: Source Protocol & Filing Navigation**

**1. Establish the Anchor Date:** Inherit the same anchor date ($D\_1$) methodology as the Senior Analyst prompt. Locate the most recent 10-K, 10-Q, or Earnings Press Release (8-K). State the exact date.

**2. Primary Geographic Source Documents:** For geographic extraction, prioritize the following sections within the anchor filing and supplementary materials, in this order:

| Priority | Source Document / Section | What to Extract |
| :---- | :---- | :---- |
| 1 | **Exhibit 21** (Subsidiaries of the Registrant) | Complete list of legal entities, their jurisdictions of incorporation, and operating countries |
| 2 | **Item 2: Properties** (10-K) | Owned/leased facilities, addresses, square footage, function |
| 3 | **Note: Segment Information** (10-K/10-Q Financial Notes) | Revenue by geographic segment, operating income by region |
| 4 | **Item 1A: Risk Factors** | Jurisdiction-specific regulatory, tax, geopolitical, and trade risks |
| 5 | **MD\&A: Geographic Revenue Discussion** | Regional revenue trends, currency exposure, market commentary |
| 6 | **Earnings Call Transcript** | Management commentary on regional performance, expansion plans, supply chain geography |
| 7 | **Investor Presentations / Capital Markets Day** | Facility maps, regional strategy slides, supply chain diagrams |
| 8 | **Press Releases** (post-$D\_1$) | New office openings, facility expansions, M\&A with geographic implications |

**3. Source Credibility Filter:** Identical to the Senior Analyst prompt:

* **Tier 1 (Highest Weight):** SEC Filings, Official Earnings Call Transcripts, Investor Presentations
* **Tier 2 (High Weight):** Bloomberg, WSJ, Reuters, FT
* **Tier 3 (Medium Weight):** Established trade publications
* **EXCLUDE:** Content farms, unverified blogs, clickbait

**4. The "Geo Claim" Rule:** Every geographic data point (location, revenue figure, risk assessment) **must** be traceable to a Tier 1 or Tier 2 source. If a location or facility cannot be verified against an official filing, mark it as `"confidence": "unverified"` in the JSON output and explain the source limitation in the narrative.

---

**PART 2: Output JSON Format Requirements**

The following defines the exact JSON output structure required for each extraction module. Produce both the structured JSON block and the corresponding narrative sections.

---

#### **MODULE A: Corporate Footprint — Offices, Facilities & Subsidiaries**

Each location in the `offices` array must follow this schema:

| Field | Description | Required? |
| :---- | :---- | :---- |
| `id` | Unique slug: `{ticker_lower}-{city_slug}-{function}` (e.g., `avgo-san-jose-hq`) | ✅ |
| `name` | Human-readable office name | ✅ |
| `city` | City name | ✅ |
| `state` | State/Province (if applicable) | If available |
| `country` | Country | ✅ |
| `address` | Full street address | If available |
| `lat` | Latitude (decimal degrees) | ✅ |
| `lng` | Longitude (decimal degrees) | ✅ |
| `type` | One of: `headquarters`, `regional`, `engineering`, `manufacturing`, `data_center`, `sales`, `satellite` | ✅ |
| `businessFocus` | Comma-separated description of primary activities | ✅ |
| `size` | Estimated headcount or square footage | If available |
| `established` | Year established or acquired | If available |
| `source` | Filing reference (e.g., "10-K FY2025, Item 2") | ✅ |
| `confidence` | `verified` (from Tier 1 source) or `unverified` | ✅ |

---

#### **MODULE B: Revenue Geography — Regional Segment Breakdown**

The `revenueGeography` object must follow this structure:

```json
"revenueGeography": {
  "fiscalYear": "FY2025",
  "totalRevenue": 63887000000,
  "currency": "USD",
  "segments": [
    {
      "region": "United States",
      "revenue": null,
      "percentage": 0.00,
      "yoyGrowth": null,
      "notes": "If exact figure unavailable, estimate from disclosures"
    }
  ],
  "concentrationRisk": "Top customer represents 32% of net revenue",
  "source": "10-K FY2025, Note 14"
}
```

---

#### **MODULE C: Supply Chain & Manufacturing Map**

Each node in the `supplyChain` array must include:

| Field | Description |
| :---- | :---- |
| `entity` | Name of the supplier/partner/facility |
| `role` | One of: `foundry`, `assembly_test`, `raw_material`, `logistics`, `contract_manufacturer`, `key_supplier` |
| `city` | City |
| `country` | Country |
| `lat` / `lng` | Coordinates |
| `product` | What is produced/supplied at this node |
| `criticality` | `critical` (single-source or irreplaceable), `important` (limited alternatives), `standard` (commodity) |
| `source` | Filing reference |

---

#### **MODULE D: Customer Concentration Geography**

Each entry in the `customerConcentration` array must follow this structure:

```json
"customerConcentration": [
  {
    "customer": "Customer A (or named if disclosed)",
    "revenueShare": "32%",
    "hqCity": "Mountain View",
    "hqCountry": "USA",
    "lat": 37.3861,
    "lng": -122.0839,
    "relationship": "Co-development partner for custom silicon",
    "source": "10-K FY2025, Note 3"
  }
]
```

---

#### **MODULE E: Regulatory & Geopolitical Risk Map**

Each entry in the `geopoliticalRisks` array must follow this structure:

```json
"geopoliticalRisks": [
  {
    "region": "China",
    "lat": 39.9042,
    "lng": 116.4074,
    "riskScore": 4,
    "riskCategory": "trade_restriction",
    "riskLabel": "US Export Controls on Advanced Semiconductors",
    "description": "Escalating US government restrictions on advanced semiconductor technology exports to Chinese customers. Company has limited direct exposure due to US hyperscaler concentration.",
    "impactLevel": "moderate",
    "filingReference": "10-K FY2025, Item 1A",
    "lastUpdated": "2025-12-11"
  }
]
```

**Risk Score Scale:**

| Score | Label | Definition |
| :---- | :---- | :---- |
| 1 | Minimal | No material risk identified in filings |
| 2 | Low | Risk mentioned in boilerplate language only |
| 3 | Moderate | Specific risk language added or expanded in recent filing |
| 4 | Elevated | Active regulatory action, litigation, or policy change affecting operations |
| 5 | Critical | Material financial impact quantified in filings (e.g., impairment, tax charge, sanctions) |

**Risk Categories:** `trade_restriction`, `regulatory_compliance`, `tax_policy`, `geopolitical_conflict`, `currency_exposure`, `environmental_regulation`, `labor_regulation`, `data_privacy`, `sanctions`, `political_instability`

---

#### **MODULE F: Strategic Expansion & Contraction Signals**

The `expansionSignals` and `contractionSignals` arrays must follow this structure:

```json
"expansionSignals": [
  {
    "type": "expansion",
    "location": "Austin, TX, USA",
    "lat": 30.2672,
    "lng": -97.7431,
    "description": "New semiconductor design center announced",
    "estimatedTimeline": "2026-2027",
    "investment": "$500M",
    "source": "Q1 2026 Earnings Call Transcript",
    "dateAnnounced": "2026-03-04"
  }
],
"contractionSignals": [
  {
    "type": "contraction",
    "location": "...",
    "description": "Office consolidation, headcount reduction",
    "source": "..."
  }
]
```

---

**PART 3: Complete JSON Output Structure**

Your complete output **must** contain both sections below, in this exact order.

---

### **SECTION 1: Structured JSON Output**

Produce a single, valid, parseable JSON object that consolidates all six modules. This JSON is designed to be directly consumed by the GeoCompany globe application.

```json
{
  "company": "[Company Name]",
  "ticker": "[TICKER]",
  "website": "[URL]",
  "sector": "[Sector]",
  "description": "[1-2 sentence company description with geographic emphasis]",
  "anchorFiling": {
    "type": "10-K",
    "date": "YYYY-MM-DD",
    "fiscalPeriod": "FY2025"
  },
  "generatedDate": "YYYY-MM-DD",

  "offices": [
    // MODULE A output — array of office objects
  ],

  "revenueGeography": {
    // MODULE B output
  },

  "supplyChain": [
    // MODULE C output — array of supply chain node objects
  ],

  "customerConcentration": [
    // MODULE D output — array of customer objects
  ],

  "geopoliticalRisks": [
    // MODULE E output — array of risk objects
  ],

  "expansionSignals": [
    // MODULE F expansion signals
  ],
  "contractionSignals": [
    // MODULE F contraction signals
  ]
}
```

> **Critical JSON Requirements:**
> - All coordinate values must use decimal degrees (e.g., `37.3861`, `-122.0839`)
> - All revenue values must be in raw numbers (no abbreviations like "$63.9B" — use `63900000000`)
> - All dates must use ISO 8601 format (`YYYY-MM-DD`)
> - The `offices` array must be compatible with the existing GeoCompany `companies.json` schema (fields: `id`, `name`, `city`, `country`, `address`, `lat`, `lng`, `businessFocus`, `size`, `type`, `established`)
> - Do NOT include trailing commas or comments in the JSON

---

### **SECTION 2: Geographic Intelligence Narrative**

Produce a professional markdown intelligence brief organized by the sections below. This narrative is rendered in the GeoCompany research panel alongside the 3D globe.

---

#### **1. Geographic Profile Summary**

A 3–5 sentence overview of the company's global footprint. Answer: *Where does this company operate, and why does geography matter to its investment thesis?*

State the total number of identified locations, the number of countries, and the primary regional concentrations.

#### **2. Headquarters & Key Facilities**

Describe the company's most strategically important locations. For each, explain:
- What function the facility serves
- Why it is strategically significant
- Any recent investments or changes

#### **3. Revenue Geography Analysis**

Interpret the regional revenue breakdown. Address:
- Which regions are growing fastest/slowest?
- Is the company over-concentrated in any single geography?
- How does currency exposure affect reported results?
- Are there markets the company is conspicuously absent from?

#### **4. Supply Chain Geographic Risk**

Assess the geographic vulnerability of the company's supply chain:
- Are there single-point-of-failure locations? (e.g., sole foundry in Taiwan)
- How diversified is the manufacturing/fulfillment footprint?
- What would a disruption in \[specific region\] mean for operations?

#### **5. Regulatory & Geopolitical Exposure**

Summarize the jurisdiction-specific risks identified in Module E, interpreted for a Portfolio Manager:
- Which regulatory risks are **new** in the latest filing?
- Which geopolitical scenarios would have the highest financial impact?
- How is management positioning the company to mitigate geographic risk?

#### **6. Strategic Geographic Outlook**

Forward-looking assessment:
- Where is the company expanding and why?
- Are there regions where the company is pulling back?
- How does the geographic strategy align with sector trends (e.g., nearshoring, data sovereignty)?

---

**PART 4: Style Guidelines**

* **Tone:** Professional, objective, institutional. This is a geographic intelligence product for a Portfolio Manager, not a blog post.
* **Precision:** Use exact figures from filings where available. Do not round unless the source itself rounds. Always state the source.
* **Formatting (Narrative):** Use H2/H3 headers, bullet points, and bold text for key metrics. Include inline citations \[1\] for every geographic claim.
* **Formatting (JSON):** Valid JSON only. Test output mentally for parse errors. No JavaScript-style comments.
* **Coordinates:** Use geocoding services or known coordinates (corporate address → lat/lng). If you cannot determine precise coordinates, use the city center and note `"confidence": "city_center_approximation"` in the source field.
* **Length:** The narrative section should be comprehensive but focused — approximately 1,500–3,000 words. The JSON section will vary by company complexity.
* **Citations:** Number all sources sequentially \[1\], \[2\], etc., and provide a "Works Cited" list at the end of the narrative section, identical in format to the Senior Analyst prompt output.
