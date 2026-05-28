#!/usr/bin/env node

/**
 * SEC 13F Holdings Fetcher for Dossigraphica
 * ===========================================
 *
 * Fetches the latest institutional holdings (13F filings) from the SEC EDGAR
 * system for all tracked companies and writes the result to
 * src/data/institutional_holders.json.
 *
 * Usage:
 *   node scripts/fetch_13f_holdings.mjs
 *
 * Or via npm:
 *   npm run update-holdings
 *
 * Data source: SEC EDGAR (https://www.sec.gov/edgar.shtml)
 * - Company ticker → CIK mapping: https://www.sec.gov/files/company_tickers.json
 * - Company submissions: https://data.sec.gov/submissions/CIK{padded_cik}.json
 * - 13F primary doc: https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primaryDoc}
 *
 * Output schema matches the TypeScript InstitutionalHoldingsMap type.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUTPUT_FILE = path.join(PROJECT_ROOT, 'src', 'data', 'institutional_holders.json');

// ── Configuration ────────────────────────────────────────────────────────────

const TRACKED_TICKERS = ['AMD', 'AMZN', 'ASML', 'AVGO', 'GOOGL', 'INTC', 'META', 'MSFT', 'MU', 'NVDA', 'TSM'];

// Known shares outstanding (approximate) — used to compute ownership_pct.
// These should be updated periodically from each company's latest 10-Q/10-K.
// You can find shares outstanding on the cover page of the latest quarterly filing.
const KNOWN_SHARES_OUTSTANDING = {
  AMD: 1_630_600_639,
  AMZN: 10_400_000_000,
  ASML: 393_000_000,
  AVGO: 4_630_000_000,
  GOOGL: 12_300_000_000,
  INTC: 4_200_000_000,
  META: 2_510_000_000,
  MSFT: 7_440_000_000,
  MU: 1_110_000_000,
  NVDA: 24_500_000_000,
  TSM: 5_190_000_000,
};

// SEC requires a User-Agent header identifying the requester.
// Update this with your name and email.
const SEC_USER_AGENT = 'Dossigraphica Research (contact@dossigraphica.example.com)';
const SEC_BASE = 'https://www.sec.gov';

// Delay between SEC API calls (ms) — EDGAR has rate limits (~10 req/s)
const SEC_RATE_LIMIT_MS = 150;

// ── Helpers ──────────────────────────────────────────────────────────────────

async function secFetch(url) {
  const response = await fetch(url, {
    headers: {
      'User-Agent': SEC_USER_AGENT,
      'Accept': 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`SEC API ${response.status}: ${url}`);
  }
  return response.json();
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function padCik(cik) {
  return String(cik).padStart(10, '0');
}

function formatCurrency(value) {
  return '$' + Math.round(value).toLocaleString('en-US');
}

// ── Core Fetching Logic ─────────────────────────────────────────────────────

async function fetchCikMap() {
  console.log('→ Fetching CIK → ticker mapping from SEC...');
  const data = await secFetch('https://www.sec.gov/files/company_tickers.json');
  // Convert from SEC's format (keys are 0, 1, 2, ...)
  const map = new Map();
  for (const entry of Object.values(data)) {
    map.set(entry.ticker, {
      cik: entry.cik_str,
      name: entry.title,
    });
  }
  console.log(`  ✓ Loaded ${map.size} company mappings`);
  return map;
}

/**
 * Fetch the latest 13F-HR filing for a given CIK.
 * Returns the primary XML document URL or null if none found.
 */
async function fetchLatest13FHr(cikPadded) {
  const url = `${SEC_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK=${cikPadded}&type=13F-HR&dateb=&owner=exclude&count=20`;
  
  // This endpoint returns HTML. We can use the submissions API instead.
  const submissionsUrl = `${SEC_BASE}/data/edgar/CIK${cikPadded}.json`;
  const submissions = await secFetch(submissionsUrl);
  
  const filings = submissions?.filings?.recent;
  if (!filings) {
    console.warn(`  ⚠ No filings data for CIK ${cikPadded}`);
    return null;
  }

  // Find the most recent 13F-HR filing
  const form13FIndex = filings.form?.findLastIndex(f => f === '13F-HR');
  if (form13FIndex === -1) {
    // Try findIndex from start
    const idx = filings.form?.indexOf('13F-HR');
    if (idx === -1) return null;
    
    return {
      accession: filings.accessionNumber[idx],
      primaryDoc: filings.primaryDocument[idx],
      filingDate: filings.filingDate[idx],
      reportDate: filings.reportDate?.[idx],
    };
  }

  return {
    accession: filings.accessionNumber[form13FIndex],
    primaryDoc: filings.primaryDocument[form13FIndex],
    filingDate: filings.filingDate[form13FIndex],
    reportDate: filings.reportDate?.[form13FIndex],
  };
}

/**
 * Parse the primary 13F document URL and extract the XML information table URL.
 * The primary doc is usually an XML file like 'form13fInfoTable.xml' or similar.
 */
function getInfoTableUrl(cik, accession, primaryDoc) {
  // Accension number format: 0001234567-25-000001
  const accessionNoDashes = accession.replace(/-/g, '');
  const base = `${SEC_BASE}/Archives/edgar/data/${cik}/${accessionNoDashes}`;

  // The primary doc name varies. Common patterns:
  // - 'primary13f.xml' or 'form13fInfoTable.xml'
  // - Sometimes the primary doc IS the info table
  if (primaryDoc?.toLowerCase().includes('infotable') || primaryDoc?.endsWith('.xml')) {
    return `${base}/${primaryDoc}`;
  }

  // Try the most common pattern
  return `${base}/form13fInfoTable.xml`;
}

/**
 * Fetch and parse the 13F holdings from an XML info table.
 * Returns an array of { name, value, shares } objects.
 */
async function parse13FHoldings(xmlUrl) {
  const response = await fetch(xmlUrl, {
    headers: { 'User-Agent': SEC_USER_AGENT },
  });
  if (!response.ok) {
    throw new Error(`XML fetch ${response.status}: ${xmlUrl}`);
  }
  const xml = await response.text();

  // Parse the XML to extract holdings
  // SEC 13F XML format varies but typically has <nameOfIssuer>, <value>, <shrsOrPrnAmt>
  const holdings = [];
  
  // Simple regex-based parsing (avoids needing an XML parser dependency)
  const tablePattern = /<infotable>?(.*?)<\/infotable>/gis;
  const issuerPattern = /<nameOfIssuer>([^<]+)<\/nameOfIssuer>/gi;
  const valuePattern = /<value>([^<]+)<\/value>/gi;
  const sharesPattern = /<shrsOrPrnAmt>(?:\s*<sshPrnamt>([^<]+)<\/sshPrnamt>)/gis;
  const putCallPattern = /<putCall>([^<]+)<\/putCall>/gi;

  // Simpler approach: extract all entries
  const entryPattern = /<?(?:infoTable|investmentDiscretion)>([\s\S]*?)<\/(?:infoTable|investmentDiscretion)>/gi;
  let match;
  
  while ((match = entryPattern.exec(xml)) !== null) {
    const block = match[1];
    
    const nameMatch = /<nameOfIssuer>([^<]+)<\/nameOfIssuer>/i.exec(block);
    const valueMatch = /<value>([^<]+)<\/value>/i.exec(block);
    const sharesMatch = /<sshPrnamt>([^<]+)<\/sshPrnamt>/i.exec(block);
    
    if (!nameMatch || !valueMatch || !sharesMatch) continue;
    
    const name = nameMatch[1].trim();
    const value = parseInt(valueMatch[1], 10) * 1000; // value is in $thousands
    const shares = parseInt(sharesMatch[1], 10);
    
    if (name && value > 0 && shares > 0) {
      holdings.push({
        institution: name,
        value,
        shares,
      });
    }
  }

  return holdings;
}

/**
 * Try to get shares outstanding from the latest 10-Q or 10-K filing.
 */
async function fetchSharesOutstanding(cikPadded, ticker) {
  if (KNOWN_SHARES_OUTSTANDING[ticker]) {
    return KNOWN_SHARES_OUTSTANDING[ticker];
  }

  try {
    const submissionsUrl = `${SEC_BASE}/data/edgar/CIK${cikPadded}.json`;
    const submissions = await secFetch(submissionsUrl);
    const filings = submissions?.filings?.recent;
    if (!filings) return null;

    // Look for the latest 10-K or 10-Q
    const forms = filings.form || [];
    for (let i = 0; i < forms.length; i++) {
      if (forms[i] === '10-K' || forms[i] === '10-Q') {
        const accession = filings.accessionNumber[i];
        const primaryDoc = filings.primaryDocument[i];
        if (!accession || !primaryDoc) continue;

        // Fetch the filing document to find shares outstanding from the cover page
        const accNoDash = accession.replace(/-/g, '');
        const docUrl = `${SEC_BASE}/Archives/edgar/data/${cikPadded.replace(/^0+/, '')}/${accNoDash}/${primaryDoc}`;
        
        const resp = await fetch(docUrl, {
          headers: { 'User-Agent': SEC_USER_AGENT },
        });
        if (!resp.ok) continue;
        
        const text = await resp.text();
        // Look for the common pattern on the cover page:
        // "Entity Common Stock, Shares Outstanding" or similar
        const soMatch = text.match(/Common Stock[^.]*?[Oo]utstanding[^0-9]*([0-9,]+)/);
        if (soMatch) {
          return parseInt(soMatch[1].replace(/,/g, ''), 10);
        }
        break; // Only check the most recent relevant filing
      }
    }
  } catch (e) {
    console.warn(`  ⚠ Could not fetch shares outstanding for ${ticker}: ${e.message}`);
  }
  
  return null;
}

/**
 * Geocode a city/country to approximate lat/lng coordinates.
 * Uses a built-in lookup table for known financial centers.
 */
function geocodeLocation(city, country) {
  const knownLocations = {
    'Malvern, US': { lat: 40.036, lng: -75.518 },
    'New York, US': { lat: 40.758, lng: -73.985 },
    'Boston, US': { lat: 42.350, lng: -71.050 },
    'San Francisco, US': { lat: 37.775, lng: -122.418 },
    'Chicago, US': { lat: 41.878, lng: -87.629 },
    'Los Angeles, US': { lat: 34.052, lng: -118.243 },
    'Houston, US': { lat: 29.760, lng: -95.369 },
    'Seattle, US': { lat: 47.606, lng: -122.332 },
    'Denver, US': { lat: 39.739, lng: -104.990 },
    'Philadelphia, US': { lat: 39.952, lng: -75.165 },
    'Stamford, US': { lat: 41.053, lng: -73.539 },
    'Greenwich, US': { lat: 41.026, lng: -73.628 },
    'London, GB': { lat: 51.507, lng: -0.127 },
    'Tokyo, JP': { lat: 35.676, lng: 139.650 },
    'Toronto, CA': { lat: 43.653, lng: -79.383 },
    'Zurich, CH': { lat: 47.376, lng: 8.542 },
    'Sydney, AU': { lat: -33.868, lng: 151.209 },
    'Hong Kong, HK': { lat: 22.319, lng: 114.169 },
    'Singapore, SG': { lat: 1.352, lng: 103.820 },
    'Taipei, TW': { lat: 25.033, lng: 121.565 },
    'Amsterdam, NL': { lat: 52.367, lng: 4.904 },
    'Paris, FR': { lat: 48.857, lng: 2.352 },
    'Frankfurt, DE': { lat: 50.110, lng: 8.682 },
  };

  const key = `${city}, ${country}`;
  const loc = knownLocations[key];
  if (loc) return loc;

  // Fallback: center of country
  const countryCenters = {
    US: { lat: 39.828, lng: -98.579 },
    GB: { lat: 55.378, lng: -3.436 },
    JP: { lat: 36.204, lng: 138.253 },
    CA: { lat: 56.130, lng: -106.347 },
    CH: { lat: 46.818, lng: 8.227 },
    AU: { lat: -25.274, lng: 133.775 },
    HK: { lat: 22.319, lng: 114.169 },
    SG: { lat: 1.352, lng: 103.820 },
    TW: { lat: 23.697, lng: 120.960 },
    NL: { lat: 52.132, lng: 5.291 },
    FR: { lat: 46.603, lng: 1.888 },
    DE: { lat: 51.165, lng: 10.451 },
  };
  return countryCenters[country] || { lat: 0, lng: 0 };
}

// Known institution headquarters for geocoding
const KNOWN_INSTITUTION_HQS = {
  'Vanguard Group Inc': { city: 'Malvern', country: 'US' },
  'BlackRock Inc': { city: 'New York', country: 'US' },
  'State Street Corp': { city: 'Boston', country: 'US' },
  'FMR LLC (Fidelity)': { city: 'Boston', country: 'US' },
  'Morgan Stanley': { city: 'New York', country: 'US' },
  'JPMorgan Chase & Co': { city: 'New York', country: 'US' },
  'Goldman Sachs Group Inc': { city: 'New York', country: 'US' },
  'Bank of New York Mellon Corp': { city: 'New York', country: 'US' },
  'Northern Trust Corp': { city: 'Chicago', country: 'US' },
  'Invesco Ltd': { city: 'Atlanta', country: 'US' },
};

// Institution name normalization
function normalizeInstitutionName(raw) {
  const name = raw.trim();
  
  // Known reverse mappings from SEC naming to canonical names
  const overrides = {
    'VANGUARD': 'Vanguard Group Inc',
    'BLACKROCK': 'BlackRock Inc',
    'STATE STREET': 'State Street Corp',
    'FMR': 'FMR LLC (Fidelity)',
    'FIDELITY': 'FMR LLC (Fidelity)',
    'MORGAN STANLEY': 'Morgan Stanley',
    'JPMORGAN': 'JPMorgan Chase & Co',
    'GOLDMAN SACHS': 'Goldman Sachs Group Inc',
    'BANK OF NEW YORK MELLON': 'Bank of New York Mellon Corp',
    'NORTHERN TRUST': 'Northern Trust Corp',
    'INVESCO': 'Invesco Ltd',
  };

  for (const [key, val] of Object.entries(overrides)) {
    if (name.toUpperCase().includes(key)) return val;
  }
  
  return name;
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('═══════════════════════════════════════════════');
  console.log('  SEC 13F Holdings Fetcher — Dossigraphica');
  console.log('═══════════════════════════════════════════════\n');

  const cikMap = await fetchCikMap();
  await delay(SEC_RATE_LIMIT_MS);

  const result = {};

  for (const ticker of TRACKED_TICKERS) {
    console.log(`\n─ ${ticker} ────────────────────────────────────`);
    
    const entry = cikMap.get(ticker);
    if (!entry) {
      console.warn(`  ⚠ No CIK found for ${ticker}, skipping`);
      continue;
    }

    const cikPadded = padCik(entry.cik);
    console.log(`  CIK: ${entry.cik} (${cikPadded})`);
    console.log(`  Name: ${entry.name}`);

    try {
      // Step 1: Find latest 13F-HR filing
      const latest13f = await fetchLatest13FHr(cikPadded);
      await delay(SEC_RATE_LIMIT_MS);

      if (!latest13f) {
        console.warn(`  ⚠ No 13F-HR filing found for ${ticker}`);
        continue;
      }

      console.log(`  Latest 13F: ${latest13f.filingDate} (period: ${latest13f.reportDate || 'N/A'})`);

      // Step 2: Fetch the info table URL and parse holdings
      const infoTableUrl = getInfoTableUrl(
        entry.cik,
        latest13f.accession,
        latest13f.primaryDoc
      );
      
      console.log(`  Fetching holdings from ${infoTableUrl}...`);
      let holdings;
      try {
        holdings = await parse13FHoldings(infoTableUrl);
      } catch (e) {
        console.warn(`  ⚠ Failed to parse holdings XML: ${e.message}`);
        holdings = [];
      }
      
      await delay(SEC_RATE_LIMIT_MS);

      if (holdings.length === 0) {
        console.warn(`  ⚠ No holdings parsed for ${ticker}`);
        continue;
      }
      
      console.log(`  Parsed ${holdings.length} holder entries`);

      // Step 3: Aggregate by institution (same institution may have multiple filings)
      const aggMap = new Map();
      for (const h of holdings) {
        const normalized = normalizeInstitutionName(h.institution);
        const existing = aggMap.get(normalized);
        if (existing) {
          existing.value += h.value;
          existing.shares += h.shares;
        } else {
          aggMap.set(normalized, { institution: normalized, value: h.value, shares: h.shares });
        }
      }

      // Step 4: Sort by value descending, take top 10
      const sorted = Array.from(aggMap.values())
        .sort((a, b) => b.value - a.value)
        .slice(0, 10);

      // Step 5: Get shares outstanding for ownership %
      const sharesOutstanding = await fetchSharesOutstanding(cikPadded, ticker);
      if (sharesOutstanding) {
        console.log(`  Shares outstanding: ${sharesOutstanding.toLocaleString()}`);
      } else {
        console.log(`  Shares outstanding: unknown (ownership % will be 0)`);
      }
      await delay(SEC_RATE_LIMIT_MS);

      // Step 6: Compute total institutional value
      const totalValue = sorted.reduce((sum, h) => sum + h.value, 0);

      // Step 7: Build the output entry
      result[ticker] = {
        company_name: entry.name,
        shares_outstanding: sharesOutstanding || 0,
        total_institutional_value: totalValue,
        top_holders: sorted.map((h, i) => {
          const hq = KNOWN_INSTITUTION_HQS[h.institution] || {};
          const geo = geocodeLocation(hq.city || h.institution, hq.country || 'US');
          const ownershipPct = sharesOutstanding > 0
            ? parseFloat(((h.shares / sharesOutstanding) * 100).toFixed(2))
            : 0;
          
          return {
            institution: h.institution,
            value: h.value,
            value_formatted: formatCurrency(h.value),
            shares: h.shares,
            ownership_pct: ownershipPct,
            ownership_pct_formatted: ownershipPct > 0 ? ownershipPct.toFixed(2) + '%' : '<0.01%',
            city: hq.city || '',
            country: hq.country || 'US',
            state: null,
            lat: geo.lat,
            lng: geo.lng,
            report_period: latest13f.reportDate || latest13f.filingDate,
            rank: i + 1,
          };
        }),
      };

      console.log(`  ✓ ${sorted.length} holders aggregated, total value: ${formatCurrency(totalValue)}`);
    } catch (e) {
      console.error(`  ✗ Failed for ${ticker}: ${e.message}`);
    }
  }

  // Write output
  const outputDir = path.dirname(OUTPUT_FILE);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(result, null, 2));
  
  const totalCompanies = Object.keys(result).length;
  const totalHolders = Object.values(result).reduce((sum, c) => sum + c.top_holders.length, 0);
  
  console.log('\n═══════════════════════════════════════════════');
  console.log(`  Wrote ${totalCompanies} companies, ${totalHolders} holders`);
  console.log(`  → ${OUTPUT_FILE}`);
  console.log('═══════════════════════════════════════════════\n');
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
