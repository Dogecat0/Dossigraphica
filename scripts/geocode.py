#!/usr/bin/env python3
"""
Batch Geocoding Script for Dossigraphica
======================================
Reads office addresses from offices_input.csv and geocodes them
using OpenStreetMap Nominatim (free, no API key needed).

Usage:
    pip install geopy
    python scripts/geocode.py

Input:  scripts/offices_input.csv
Output: src/data/companies.json

Nominatim usage policy:
- Max 1 request/sec (enforced by RateLimiter)
- Must include a valid User-Agent
- Data © OpenStreetMap contributors (ODbL license)
"""

import csv
import json
import os
import sys
from collections import defaultdict

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except ImportError:
    print("Error: geopy is required. Install it with:")
    print("  pip install geopy")
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
INPUT_CSV = os.path.join(SCRIPT_DIR, "offices_input.csv")
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "src", "data", "companies.json")

# Company-level metadata (add more companies here)
COMPANY_META = {
    "Alphabet Inc.": {
        "website": "https://abc.xyz",
        "ticker": "GOOGL",
        "sector": "Technology / Communication Services",
        "description": "A global technology conglomerate with a massive footprint spanning sovereign-level infrastructure, characterized by highly concentrated corporate hubs and geographically dispersed, energy-intensive data centers powering global search, cloud, and generative AI.",
    },
    "Microsoft": {
        "website": "https://www.microsoft.com/",
        "ticker": "MSFT",
        "sector": "Technology",
        "description": "A multinational technology corporation producing computer software, consumer electronics, and personal computers. Known for Windows, Office 365, Azure, LinkedIn, GitHub, and Xbox.",
    },
    "Broadcom Inc.": {
        "website": "https://www.broadcom.com",
        "ticker": "AVGO",
        "sector": "Semiconductor and Infrastructure Software",
        "description": "A global technology leader designing, developing, and supplying semiconductor and infrastructure software solutions.",
    },
    "Amazon.com": {
        "website": "https://www.amazon.com",
        "ticker": "AMZN",
        "sector": "Consumer Discretionary / Technology",
        "description": "Amazon is a multinational technology conglomerate operating a globally distributed corporate footprint, featuring a highly bifurcated architecture that separates its legacy retail fulfillment logistics, its hyperscale AWS cloud computing infrastructure, and its emerging low Earth orbit (LEO) satellite manufacturing operations.",
    },
}


def slugify(text):
    """Convert text to a URL-safe slug."""
    return text.lower().replace(" ", "-").replace(",", "").replace(".", "")


def geocode_offices(input_csv):
    """Read CSV and geocode each address using Nominatim."""

    geolocator = Nominatim(user_agent="dossigraphica-batch-geocoder/1.0")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)

    offices_by_company = defaultdict(list)

    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            company = row["company"].strip()
            office_name = row["office_name"].strip()
            address = row["address"].strip()
            business_focus = row.get("business_focus", "").strip()
            size = row.get("size", "").strip()
            office_type = row.get("type", "satellite").strip()
            established = row.get("established", "").strip()

            print(f"  [{i+1}] Geocoding: {office_name} ({address})...", end=" ")

            location = geocode(address)

            if location:
                lat = round(location.latitude, 4)
                lng = round(location.longitude, 4)
                print(f"✓ ({lat}, {lng})")
            else:
                print("✗ NOT FOUND — skipping")
                continue

            # Extract city and country from address (simple heuristic)
            parts = [p.strip() for p in address.split(",")]
            city = parts[0] if len(parts) >= 2 else address
            country = parts[-1] if len(parts) >= 2 else "Unknown"

            office = {
                "id": slugify(f"{company[:4]}-{office_name}"),
                "name": office_name,
                "city": city,
                "country": country,
                "address": address,
                "lat": lat,
                "lng": lng,
                "businessFocus": business_focus,
                "size": size,
                "type": office_type,
            }

            if established:
                office["established"] = established

            offices_by_company[company].append(office)

    return offices_by_company


def build_json(offices_by_company):
    """Build the companies.json structure."""
    companies = []

    for company_name, offices in offices_by_company.items():
        meta = COMPANY_META.get(company_name, {})
        companies.append(
            {
                "company": company_name,
                "website": meta.get("website", ""),
                "ticker": meta.get("ticker", ""),
                "sector": meta.get("sector", ""),
                "description": meta.get("description", ""),
                "offices": offices,
            }
        )

    return companies


def main():
    print(f"\n🌍 Dossigraphica Batch Geocoder")
    print(f"{'─' * 40}")

    if not os.path.exists(INPUT_CSV):
        print(f"\n❌ Input file not found: {INPUT_CSV}")
        print(f"   Create it with columns: company, office_name, address, business_focus, size, type, established")
        sys.exit(1)

    print(f"📄 Reading: {INPUT_CSV}")
    offices_by_company = geocode_offices(INPUT_CSV)

    total_offices = sum(len(v) for v in offices_by_company.values())
    print(f"\n✅ Geocoded {total_offices} offices for {len(offices_by_company)} companies")

    companies = build_json(offices_by_company)

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)

    print(f"💾 Written: {OUTPUT_JSON}")
    print(f"\n🎉 Done! Start the dev server with: npm run dev\n")


if __name__ == "__main__":
    main()
