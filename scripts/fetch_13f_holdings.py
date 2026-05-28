#!/usr/bin/env python3
"""
SEC 13F Holdings Fetcher for Dossigraphica
============================================

Fetches the latest institutional holdings (13F filings) from SEC EDGAR for
all tracked companies and writes top-10 holders per entity to
src/data/institutional_holders.json.

Strategy:
  - Defines a known set of the largest institutional investment managers.
  - Fetches each manager's latest 13F-HR filing from EDGAR.
  - Parses the XML info table to extract holdings.
  - Maps each holding to tracked companies.
  - For each tracked company, aggregates by institution, sorts by value, takes top 10.
  - Computes ownership % using shares outstanding.

Usage:
    pip install httpx       # already in requirements.txt
    python scripts/fetch_13f_holdings.py

Or via npm:
    npm run update-holdings
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import httpx

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = PROJECT_ROOT / "src" / "data" / "institutional_holders.json"

# ── Tracked Companies ────────────────────────────────────────────────────────

TRACKED_TICKERS = ["AMD", "AMZN", "ASML", "AVGO", "GOOGL", "INTC", "META", "MSFT", "MU", "NVDA", "TSM"]

# ── Shares Outstanding (approximate) ─────────────────────────────────────────
# Used to compute ownership_pct. Update from each company's latest 10-Q/10-K.
# Found on the cover page: "Entity Common Stock, Shares Outstanding"
SHARES_OUTSTANDING = {
    "AMD": 1_630_600_639,
    "AMZN": 10_400_000_000,
    "ASML": 393_000_000,
    "AVGO": 4_630_000_000,
    "GOOGL": 12_300_000_000,
    "INTC": 4_200_000_000,
    "META": 2_510_000_000,
    "MSFT": 7_440_000_000,
    "MU": 1_110_000_000,
    "NVDA": 24_500_000_000,
    "TSM": 5_190_000_000,
}

# ── Known Major Institutional Managers ───────────────────────────────────────
# CIKs for the largest 13F filers. These are the managers whose 13F filings
# we fetch to build the holdings dataset. Add or update as needed.
# CIKs can be found at: https://www.sec.gov/files/company_tickers.json
# (investment managers also have CIK entries there)
MAJOR_MANAGERS = [
    # Name                             CIK
    ("Vanguard Group Inc",              1047877),  # Largest
    ("BlackRock Inc",                   1364742),
    ("State Street Corp",               93751),
    ("FMR LLC (Fidelity)",              315066),
    ("Morgan Stanley",                   895421),
    ("JPMorgan Chase & Co",             19617),
    ("Goldman Sachs Group Inc",          886982),
    ("Bank of New York Mellon Corp",     1390777),
    ("Northern Trust Corp",              73124),
    ("Invesco Ltd",                      914208),
    ("Capital World Investors",          973118),   # Capital Group
    ("Capital Research Global Investors", 1091677),
    ("T. Rowe Price Associates Inc",     1116938),
    ("Geode Capital Management LLC",     1028942),
    ("Legal & General Group PLC",        1103978),
    ("Wellington Management Group LLP",  1089114),
    ("Dimensional Fund Advisors LP",     1059205),
    ("Charles Schwab Investment Mgmt",   1105847),
    ("Ameriprise Financial Inc",         1013685),
    ("Norges Bank Investment Mgmt",      1227457),
    ("Mitsubishi UFJ Financial Group",   1098950),
    ("UBS Group AG",                     1114448),
    ("Deutsche Bank AG",                 1159506),
    ("Credit Suisse Group AG",           1084204),
    ("BNP Paribas SA",                   1119586),
    ("Barclays PLC",                      81258),
    ("Citigroup Inc",                     705841),
    ("Bank of America Corp",             70858),
    ("Wells Fargo & Co",                   72971),
    ("Prudential Financial Inc",          1137774),
    ("MetLife Inc",                       1364743),
    ("AIG Inc",                            5272),
]

# Known institution HQ locations for geocoding
KNOWN_HQS = {
    "Vanguard Group Inc":           ("Malvern", "US"),
    "BlackRock Inc":                ("New York", "US"),
    "State Street Corp":            ("Boston", "US"),
    "FMR LLC (Fidelity)":           ("Boston", "US"),
    "Morgan Stanley":               ("New York", "US"),
    "JPMorgan Chase & Co":          ("New York", "US"),
    "Goldman Sachs Group Inc":      ("New York", "US"),
    "Bank of New York Mellon Corp": ("New York", "US"),
    "Northern Trust Corp":          ("Chicago", "US"),
    "Invesco Ltd":                  ("Atlanta", "US"),
    "Capital World Investors":      ("Los Angeles", "US"),
    "T. Rowe Price Associates Inc": ("Baltimore", "US"),
    "Charles Schwab Investment Mgmt": ("San Francisco", "US"),
    "Ameriprise Financial Inc":     ("Minneapolis", "US"),
    "UBS Group AG":                 ("Zurich", "CH"),
    "Deutsche Bank AG":             ("Frankfurt", "DE"),
    "Credit Suisse Group AG":       ("Zurich", "CH"),
    "BNP Paribas SA":               ("Paris", "FR"),
    "Barclays PLC":                 ("London", "GB"),
    "Bank of America Corp":         ("Charlotte", "US"),
    "Wells Fargo & Co":             ("San Francisco", "US"),
    "Citigroup Inc":                ("New York", "US"),
}

# Country coordinate centers for fallback geocoding
COUNTRY_CENTERS = {
    "US": (39.828, -98.579),
    "GB": (55.378, -3.436),
    "CH": (46.818, 8.227),
    "DE": (51.165, 10.451),
    "FR": (46.603, 1.888),
    "JP": (36.204, 138.253),
    "CA": (56.130, -106.347),
    "AU": (-25.274, 133.775),
    "NL": (52.132, 5.291),
    "SG": (1.352, 103.820),
    "TW": (23.697, 120.960),
    "HK": (22.319, 114.169),
}


# ── Helpers ──────────────────────────────────────────────────────────────────

SEC_BASE = "https://www.sec.gov"
SEC_USER_AGENT = "Dossigraphica Research (contact@dossigraphica.example.com)"
SEC_RATE_LIMIT_S = 0.15  # delay between requests


def fmt_currency(value: int) -> str:
    return f"${value:,}"


def pad_cik(cik: int) -> str:
    return str(cik).zfill(10)


def geocode(city: str, country: str) -> tuple[float, float]:
    """Look up lat/lng for a known city+country, falling back to country center."""
    known = {
        ("Malvern", "US"):      (40.036, -75.518),
        ("New York", "US"):     (40.758, -73.985),
        ("Boston", "US"):       (42.350, -71.050),
        ("Chicago", "US"):      (41.878, -87.629),
        ("San Francisco", "US"):(37.775, -122.418),
        ("Los Angeles", "US"):  (34.052, -118.243),
        ("Atlanta", "US"):      (33.749, -84.388),
        ("Charlotte", "US"):    (35.227, -80.843),
        ("Baltimore", "US"):    (39.290, -76.612),
        ("Minneapolis", "US"):  (44.977, -93.265),
        ("Zurich", "CH"):       (47.376, 8.542),
        ("Frankfurt", "DE"):    (50.110, 8.682),
        ("Paris", "FR"):        (48.857, 2.352),
        ("London", "GB"):       (51.507, -0.127),
    }
    loc = known.get((city, country))
    if loc:
        return loc
    fallback = COUNTRY_CENTERS.get(country, (0, 0))
    return fallback


def normalize_name(raw: str) -> str:
    """Normalize institution names from SEC filings to canonical form."""
    name = raw.strip()
    overrides = {
        "VANGUARD": "Vanguard Group Inc",
        "BLACKROCK": "BlackRock Inc",
        "STATE STREET": "State Street Corp",
        "FMR": "FMR LLC (Fidelity)",
        "FIDELITY": "FMR LLC (Fidelity)",
        "MORGAN STANLEY": "Morgan Stanley",
        "JPMORGAN": "JPMorgan Chase & Co",
        "GOLDMAN SACHS": "Goldman Sachs Group Inc",
        "BANK OF NEW YORK MELLON": "Bank of New York Mellon Corp",
        "NORTHERN TRUST": "Northern Trust Corp",
        "INVESCO": "Invesco Ltd",
        "T. ROWE PRICE": "T. Rowe Price Associates Inc",
        "CAPITAL WORLD INVESTORS": "Capital World Investors",
        "CHARLES SCHWAB": "Charles Schwab Investment Mgmt",
        "WELLINGTON": "Wellington Management Group LLP",
        "DIMENSIONAL FUND": "Dimensional Fund Advisors LP",
        "AMERIPRISE": "Ameriprise Financial Inc",
        "NORGES BANK": "Norges Bank Investment Mgmt",
        "UBS": "UBS Group AG",
        "DEUTSCHE BANK": "Deutsche Bank AG",
        "CREDIT SUISSE": "Credit Suisse Group AG",
        "CRÉDIT SUISSE": "Credit Suisse Group AG",
        "BNP PARIBAS": "BNP Paribas SA",
        "BARCLAYS": "Barclays PLC",
        "CITIGROUP": "Citigroup Inc",
        "BANK OF AMERICA": "Bank of America Corp",
        "WELLS FARGO": "Wells Fargo & Co",
        "PRUDENTIAL": "Prudential Financial Inc",
        "METLIFE": "MetLife Inc",
    }
    for key, val in overrides.items():
        if key in name.upper():
            return val
    return name


# ── SEC API ──────────────────────────────────────────────────────────────────

def sec_get(client: httpx.Client, url: str) -> str:
    """Fetch from SEC EDGAR with rate limiting and User-Agent."""
    time.sleep(SEC_RATE_LIMIT_S)
    r = client.get(url, headers={
        "User-Agent": SEC_USER_AGENT,
        "Accept": "application/json, text/xml, text/html, */*",
    })
    r.raise_for_status()
    return r.text


def fetch_manager_13f(client: httpx.Client, cik: int, manager_name: str) -> dict | None:
    """Fetch the latest 13F-HR filing for a manager, returning holding data keyed by ticker."""
    cik_padded = pad_cik(cik)

    # Get submissions overview
    url = f"{SEC_BASE}/data/edgar/CIK{cik_padded}.json"
    try:
        text = sec_get(client, url)
    except httpx.HTTPStatusError as e:
        print(f"  ⚠  {manager_name}: HTTP {e.response.status_code}")
        return None

    submissions = json.loads(text)
    filings = submissions.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    filing_dates = filings.get("filingDate", [])
    report_dates = filings.get("reportDate", [])

    # Find the most recent 13F-HR
    idx = None
    for i, form in enumerate(forms):
        if form == "13F-HR":
            idx = i
            break

    if idx is None:
        print(f"  ⚠  {manager_name}: No 13F-HR filing found")
        return None

    accession = accession_numbers[idx]
    primary_doc = primary_docs[idx]
    filing_date = filing_dates[idx]
    report_date = report_dates[idx] if idx < len(report_dates) else ""

    # Build info table URL
    acc_no_dash = accession.replace("-", "")
    cik_str = str(cik)
    info_url = f"{SEC_BASE}/Archives/edgar/data/{cik_str}/{acc_no_dash}/{primary_doc}"

    # Try primary doc first; if it doesn't end with .xml, try infoTable.xml
    if not primary_doc.lower().endswith(".xml"):
        info_url = f"{SEC_BASE}/Archives/edgar/data/{cik_str}/{acc_no_dash}/form13fInfoTable.xml"

    # Fetch the XML info table
    try:
        xml_text = sec_get(client, info_url)
    except httpx.HTTPStatusError:
        # Try alternative: /primary.xml
        info_url = f"{SEC_BASE}/Archives/edgar/data/{cik_str}/{acc_no_dash}/primary.xml"
        try:
            xml_text = sec_get(client, info_url)
        except httpx.HTTPStatusError:
            print(f"  ⚠  {manager_name}: Could not fetch info table XML")
            return None

    # Parse XML to extract holdings
    holdings = parse_13f_xml(xml_text, manager_name)
    if not holdings:
        print(f"  ⚠  {manager_name}: No holdings parsed from XML")
        return None

    print(f"  ✓  {manager_name}: {len(holdings)} holdings, filed {filing_date}")
    return {
        "manager_name": manager_name,
        "filing_date": filing_date,
        "report_date": report_date,
        "holdings": holdings,
    }


def parse_13f_xml(xml_text: str, manager_name: str) -> list[dict]:
    """Parse a 13F XML info table, returning list of {ticker, name, value, shares}."""
    holdings = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        # Try to find XML content within a non-XML wrapper
        match = re.search(r'<\?xml.*?>.*?(<[a-zA-Z].*)', xml_text, re.DOTALL)
        if match:
            try:
                root = ET.fromstring(match.group(1))
            except ET.ParseError:
                return holdings
        else:
            return holdings

    # SEC 13F XML namespace varies. Try common patterns.
    ns = {"ns": "http://www.sec.gov/edgar/thirteenf"} if "thirteenf" in xml_text else {}

    # Find all infoTable elements
    tables = root.findall(".//infoTable") or root.findall(".//ns:infoTable", ns)
    if not tables:
        # Try investmentDiscretion variant
        tables = root.findall(".//investmentDiscretion") or []

    for table in tables:
        # Extract fields
        name_of_issuer = table.findtext("nameOfIssuer") or table.findtext("ns:nameOfIssuer", "", ns)
        if not name_of_issuer:
            continue

        value_text = table.findtext("value") or table.findtext("ns:value", "", ns)
        shares_text = ""
        ssh_node = table.find("shrsOrPrnAmt") or table.find("ns:shrsOrPrnAmt", ns)
        if ssh_node is not None:
            shares_text = ssh_node.findtext("sshPrnamt") or ssh_node.findtext("ns:sshPrnamt", "", ns)

        if not value_text or not shares_text:
            continue

        value = int(value_text) * 1000  # value is in $thousands
        shares = int(shares_text)

        if value > 0 and shares > 0:
            holdings.append({
                "company_name": name_of_issuer.strip(),
                "value": value,
                "shares": shares,
            })

    return holdings


def fetch_cik_map(client: httpx.Client) -> dict[str, int]:
    """Fetch the CIK→ticker mapping from SEC."""
    print("→ Fetching CIK→ticker mapping from SEC...")
    text = sec_get(client, "https://www.sec.gov/files/company_tickers.json")
    data = json.loads(text)
    mapping = {}
    for entry in data.values():
        mapping[entry["ticker"]] = entry["cik_str"]
    print(f"  ✓ Loaded {len(mapping)} company mappings")
    return mapping


def fetch_company_info(client: httpx.Client, cik: int, ticker: str) -> str | None:
    """Fetch the company name from SEC submissions data."""
    cik_padded = pad_cik(cik)
    url = f"{SEC_BASE}/data/edgar/CIK{cik_padded}.json"
    try:
        text = sec_get(client, url)
        data = json.loads(text)
        return data.get("name", ticker)
    except Exception:
        return ticker


# ── Ticker → CIK Mapping (for companies, not managers) ──────────────────────

def build_ticker_cik_map(client: httpx.Client) -> dict[str, int]:
    """Build a ticker→CIK map from SEC."""
    text = sec_get(client, "https://www.sec.gov/files/company_tickers.json")
    data = json.loads(text)
    return {entry["ticker"]: entry["cik_str"] for entry in data.values()}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch SEC 13F holdings for tracked companies")
    parser.add_argument("--out", type=str, default=str(OUTPUT_FILE),
                        help=f"Output file (default: {OUTPUT_FILE})")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max holders per company (default: 10)")
    args = parser.parse_args()

    output_path = Path(args.out)
    max_holders = args.limit

    print("═" * 60)
    print("  SEC 13F Holdings Fetcher — Dossigraphica")
    print("═" * 60)

    with httpx.Client(verify=True, timeout=30.0) as client:
        # Step 1: Get CIK mapping for tracked companies
        cik_map = build_ticker_cik_map(client)

        # Step 2: Get company names from SEC
        company_names = {}
        for ticker in TRACKED_TICKERS:
            cik = cik_map.get(ticker)
            if cik:
                name = fetch_company_info(client, cik, ticker)
                company_names[ticker] = name
                print(f"  {ticker} → CIK {cik} → {name}")
            else:
                print(f"  ⚠  {ticker}: No CIK found")

        # Step 3: Fetch each major manager's 13F and collect holdings keyed by ticker
        print(f"\n→ Fetching 13F filings from {len(MAJOR_MANAGERS)} major managers...")

        # holdings_by_ticker: ticker -> [(manager_name, value, shares, report_period)]
        holdings_by_ticker = defaultdict(list)

        for mgr_name, mgr_cik in MAJOR_MANAGERS:
            print(f"\n  [{mgr_name}] (CIK {mgr_cik})")
            result = fetch_manager_13f(client, mgr_cik, mgr_name)
            if not result:
                continue

            report_period = result["report_date"] or result["filing_date"]

            # For each holding, check if it matches a tracked company
            for holding in result["holdings"]:
                company = holding["company_name"].upper()

                # Try to match by name against tracked companies
                matched_ticker = None
                for ticker in TRACKED_TICKERS:
                    cn = company_names.get(ticker, "").upper()
                    if company in cn or cn in company:
                        matched_ticker = ticker
                        break

                # Also try simple name fragments
                if not matched_ticker:
                    name_map = {
                        "ADVANCED MICRO": "AMD",
                        "MICROSOFT": "MSFT",
                        "AMAZON": "AMZN",
                        "ALPHABET": "GOOGL",
                        "META": "META",
                        "FACEBOOK": "META",
                        "NVIDIA": "NVDA",
                        "BROADCOM": "AVGO",
                        "AVAGO": "AVGO",
                        "MICRON": "MU",
                        "INTEL": "INTC",
                        "TAIWAN SEMICONDUCTOR": "TSM",
                        "ASML": "ASML",
                    }
                    for key, ticker in name_map.items():
                        if key in company:
                            matched_ticker = ticker
                            break

                if matched_ticker:
                    holdings_by_ticker[matched_ticker].append((
                        result["manager_name"],
                        holding["value"],
                        holding["shares"],
                        report_period,
                    ))

        # Step 4: For each tracked company, aggregate by institution, sort, take top N
        print(f"\n→ Aggregating holdings...")

        output = {}
        for ticker in TRACKED_TICKERS:
            raw = holdings_by_ticker.get(ticker, [])
            if not raw:
                print(f"  {ticker}: No holdings found")
                continue

            # Aggregate by institution
            agg = defaultdict(lambda: {"value": 0, "shares": 0, "period": ""})
            for mgr_name, value, shares, period in raw:
                agg[mgr_name]["value"] += value
                agg[mgr_name]["shares"] += shares
                if period > agg[mgr_name]["period"]:
                    agg[mgr_name]["period"] = period

            # Sort by value descending, take top N
            sorted_holders = sorted(agg.items(), key=lambda x: -x[1]["value"])[:max_holders]

            shares_outstanding = SHARES_OUTSTANDING.get(ticker, 0)
            total_value = sum(h["value"] for _, h in sorted_holders)

            holders_out = []
            shown_names = set()
            for rank, (name, data) in enumerate(sorted_holders, 1):
                ownership_pct = round((data["shares"] / shares_outstanding) * 100, 2) if shares_outstanding > 0 else 0
                owner = data

                canon_name = normalize_name(name)
                if canon_name in shown_names:
                    # Skip duplicate canonical name (shouldn't happen after aggregation, but safety)
                    continue
                shown_names.add(canon_name)

                hq = KNOWN_HQS.get(canon_name, ("", ""))
                lat, lng = geocode(hq[0], hq[1])

                holders_out.append({
                    "institution": canon_name,
                    "value": owner["value"],
                    "value_formatted": fmt_currency(owner["value"]),
                    "shares": owner["shares"],
                    "ownership_pct": ownership_pct,
                    "ownership_pct_formatted": f"{ownership_pct:.2f}%" if ownership_pct > 0 else "<0.01%",
                    "city": hq[0],
                    "country": hq[1],
                    "state": None,
                    "lat": lat,
                    "lng": lng,
                    "report_period": owner["period"],
                    "rank": rank,
                })

            # Fill remaining slots with placeholder entries if we have fewer than max_holders
            while len(holders_out) < max_holders:
                rank = len(holders_out) + 1
                holders_out.append({
                    "institution": "(other filers)",
                    "value": 0,
                    "value_formatted": "$0",
                    "shares": 0,
                    "ownership_pct": 0,
                    "ownership_pct_formatted": "0.00%",
                    "city": "",
                    "country": "US",
                    "state": None,
                    "lat": 0,
                    "lng": 0,
                    "report_period": "",
                    "rank": rank,
                })

            output[ticker] = {
                "company_name": company_names.get(ticker, ticker),
                "shares_outstanding": shares_outstanding,
                "total_institutional_value": total_value,
                "top_holders": holders_out,
            }

            print(f"  {ticker}: {len(sorted_holders)} holders aggregated → {fmt_currency(total_value)}")

        # Step 5: Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, indent=2))

        total_companies = len(output)
        total_holders = sum(len(c["top_holders"]) for c in output.values())

        print(f"\n{'═' * 60}")
        print(f"  Wrote {total_companies} companies, {total_holders} holders")
        print(f"  → {output_path}")
        print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
