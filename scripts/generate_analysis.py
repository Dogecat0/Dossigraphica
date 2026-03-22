#!/usr/bin/env python3
"""
Analysis Generator for Dossigraphica
====================================
Aggregates individual company intel files into cross-company analysis files:
- chain_matrix.json
- risk_convergence.json
- chokepoint_analysis.json

Usage:
    python scripts/generate_analysis.py
"""

import json
import os
import glob
import re
from datetime import datetime
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
INTEL_DIR = os.path.join(PROJECT_ROOT, "public", "data", "intel")
RESEARCH_DIR = os.path.join(PROJECT_ROOT, "public", "data", "research")

def load_all_intel():
    intel_files = glob.glob(os.path.join(INTEL_DIR, "*.json"))
    all_intel = []
    for file_path in sorted(intel_files):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                all_intel.append(json.load(f))
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    return all_intel

def generate_chain_matrix(all_intel):
    dependencies = []
    
    # Map from company name to ticker for easier resolution
    name_to_ticker = {intel['company']: intel['ticker'] for intel in all_intel}
    # Also map from common variations if needed
    name_to_ticker.update({
        "TSMC": "TSM",
        "Taiwan Semiconductor Manufacturing Company (TSMC)": "TSM",
        "Taiwan Semiconductor Manufacturing Company Limited": "TSM",
        "NVIDIA": "NVDA",
        "Nvidia Corporation": "NVDA",
        "Microsoft": "MSFT",
        "Microsoft Corporation": "MSFT",
        "Amazon": "AMZN",
        "Amazon.com, Inc.": "AMZN",
        "Google": "GOOGL",
        "Alphabet Inc.": "GOOGL",
        "Apple": "AAPL",
        "Apple Inc.": "AAPL",
        "Meta Platforms": "META",
        "Meta": "META",
        "Meta Platforms, Inc.": "META",
        "Broadcom": "AVGO",
        "Broadcom Inc.": "AVGO",
        "ASML": "ASML",
        "ASML Holding N.V.": "ASML",
        "Intel": "INTC",
        "Intel Corporation": "INTC",
        "Micron": "MU",
        "Micron Technology, Inc.": "MU",
        "AMD": "AMD",
        "Advanced Micro Devices, Inc.": "AMD",
        "Samsung": "005930.KS", # Using ticker placeholder
        "Samsung Electronics Co., Ltd.": "005930.KS",
        "SK Hynix": "000660.KS",
        "SK Hynix Inc.": "000660.KS"
    })

    def parse_revenue_share(share_str):
        if not share_str or "Undisclosed" in share_str:
            return 0.0
        # Handle "11-15% (Proj.)" or "22%"
        match = re.search(r"(\d+(\.\d+)?)", share_str)
        if match:
            return float(match.group(1))
        return 0.0

    for intel in all_intel:
        ticker = intel['ticker']
        
        # 1. Supply Chain (Supplier -> Company)
        for supplier in intel.get('supplyChain', []):
            supplier_entity = supplier['entity']
            # Try to resolve supplier ticker
            to_ticker = name_to_ticker.get(supplier_entity, supplier_entity)
            
            dependencies.append({
                "from": ticker,
                "to": to_ticker,
                "type": "buyer_supplier",
                "description": f"{ticker} depends on {supplier_entity} for {supplier['product']}",
                "strength": supplier['criticality'],
                "value": supplier['role']
            })
            
        # 2. Customer Concentration (Customer -> Company)
        for customer in intel.get('customerConcentration', []):
            customer_name = customer['customer']
            # Extract common name from "(Identified via intelligence as ...)"
            if "as " in customer_name:
                resolved_name = customer_name.split("as ")[1].strip(")")
            elif "(" in customer_name:
                # Handle "Customer A (Apple Inc.)"
                match = re.search(r"\((.*?)\)", customer_name)
                if match:
                    resolved_name = match.group(1)
                else:
                    resolved_name = customer_name
            else:
                resolved_name = customer_name
                
            to_ticker = name_to_ticker.get(resolved_name, resolved_name)
            
            share_val = parse_revenue_share(customer['revenueShare'])
            
            dependencies.append({
                "from": to_ticker,
                "to": ticker,
                "type": "buyer_supplier",
                "description": f"{resolved_name} is a major customer of {ticker}",
                "strength": "critical" if share_val > 10 else "important",
                "value": customer['revenueShare']
            })

    return {
        "lastUpdated": datetime.now().isoformat(),
        "version": "1.0.0",
        "dependencies": dependencies
    }

def generate_risk_convergence(all_intel):
    regional_risks = defaultdict(lambda: {
        "region": "",
        "lat": 0,
        "lng": 0,
        "contributingCompanies": [],
        "riskDimensions": set(),
        "totalScore": 0,
        "count": 0
    })

    for intel in all_intel:
        ticker = intel['ticker']
        for risk in intel.get('geopoliticalRisks', []):
            region = risk['region']
            key = region.lower()
            
            node = regional_risks[key]
            node["region"] = region
            node["lat"] = risk['lat']
            node["lng"] = risk['lng']
            node["contributingCompanies"].append({
                "ticker": ticker,
                "riskScore": risk['riskScore'],
                "impactLevel": risk['impactLevel'],
                "category": risk['riskCategory']
            })
            node["riskDimensions"].add(risk['riskCategory'])
            node["totalScore"] += risk['riskScore']
            node["count"] += 1

    regions = []
    for key, data in regional_risks.items():
        avg_score = min(10, (data["totalScore"] / data["count"]) * 2) # Normalize to 1-10 scale
        regions.append({
            "region": data["region"],
            "lat": data["lat"],
            "lng": data["lng"],
            "overallScore": round(avg_score, 1),
            "contributingCompanies": data["contributingCompanies"],
            "riskDimensions": list(data["riskDimensions"]),
            "summary": f"Aggregated risk from {data['count']} companies in {data['region']}."
        })

    return {
        "lastUpdated": datetime.now().isoformat(),
        "regions": regions
    }

def generate_chokepoint_analysis(all_intel):
    chokepoints_map = defaultdict(lambda: {
        "name": "",
        "type": "",
        "location": "",
        "lat": 0,
        "lng": 0,
        "severity": "low",
        "description": "",
        "exposedCompanies": set()
    })

    # Manual chokepoint identification logic based on common patterns
    # In a real scenario, this might be more sophisticated
    
    # 1. TSMC Hsinchu
    for intel in all_intel:
        for sc in intel.get('supplyChain', []):
            if "TSMC" in sc['entity'] and "Hsinchu" in sc['city']:
                cp = chokepoints_map["tsmc_hsinchu"]
                cp["name"] = "TSMC Hsinchu Hub"
                cp["type"] = "Manufacturing"
                cp["location"] = "Hsinchu, Taiwan"
                cp["lat"] = sc['lat']
                cp["lng"] = sc['lng']
                cp["severity"] = "critical"
                cp["description"] = "Concentration of leading-edge semiconductor manufacturing."
                cp["exposedCompanies"].add(intel['ticker'])

    # 2. ASML EUV
    for intel in all_intel:
        # Check if they depend on ASML or EUV (ASML.json itself or customers of ASML)
        if intel['ticker'] == 'ASML':
            cp = chokepoints_map["asml_euv"]
            cp["name"] = "ASML EUV Monopsony"
            cp["type"] = "Equipment"
            cp["location"] = "Veldhoven, Netherlands"
            cp["lat"] = intel['offices'][0]['lat'] if intel['offices'] else 51.4231
            cp["lng"] = intel['offices'][0]['lng'] if intel['offices'] else 5.3857
            cp["severity"] = "critical"
            cp["description"] = "Sole provider of EUV lithography systems."
            # Exposed companies are those who buy from ASML (TSMC, Intel, Samsung)
            # This would ideally come from ASML's customer list
        
        for sc in intel.get('supplyChain', []):
            if "ASML" in sc['entity']:
                cp = chokepoints_map["asml_euv"]
                cp["exposedCompanies"].add(intel['ticker'])

    chokepoints = []
    for cp_id, data in chokepoints_map.items():
        data["exposedCompanies"] = list(data["exposedCompanies"])
        data["id"] = cp_id
        data["mitigationStatus"] = "Developing"
        chokepoints.append(data)

    return {
        "lastUpdated": datetime.now().isoformat(),
        "chokepoints": chokepoints
    }

def main():
    print("🚀 Generating Cross-Company Analysis Data...")
    all_intel = load_all_intel()
    
    if not all_intel:
        print("❌ No intel data found. Exiting.")
        return

    os.makedirs(RESEARCH_DIR, exist_ok=True)

    # 1. Chain Matrix
    chain_matrix = generate_chain_matrix(all_intel)
    with open(os.path.join(RESEARCH_DIR, "chain_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(chain_matrix, f, indent=2)
    print(f"  ✓ Generated: chain_matrix.json ({len(chain_matrix['dependencies'])} links)")

    # 2. Risk Convergence
    risk_convergence = generate_risk_convergence(all_intel)
    with open(os.path.join(RESEARCH_DIR, "risk_convergence.json"), "w", encoding="utf-8") as f:
        json.dump(risk_convergence, f, indent=2)
    print(f"  ✓ Generated: risk_convergence.json ({len(risk_convergence['regions'])} regions)")

    # 3. Chokepoint Analysis
    chokepoint_analysis = generate_chokepoint_analysis(all_intel)
    with open(os.path.join(RESEARCH_DIR, "chokepoint_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(chokepoint_analysis, f, indent=2)
    print(f"  ✓ Generated: chokepoint_analysis.json ({len(chokepoint_analysis['chokepoints'])} chokepoints)")

    print("\n✅ Analysis generation complete.")

if __name__ == "__main__":
    main()
