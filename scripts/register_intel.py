#!/usr/bin/env python3
"""
Intel Registry Script for Dossigraphica
=======================================
Automatically builds the master companies.json list by scanning 
the high-fidelity research files in public/data/intel/*.json.

This replaces the manual CSV/Geocoding workflow.

Usage:
    python scripts/register_intel.py
"""

import json
import os
import glob

# ── Configuration ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
INTEL_DIR = os.path.join(PROJECT_ROOT, "public", "data", "intel")
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "src", "data", "companies.json")

def main():
    print(f"\n📂 Dossigraphica Intel Registry")
    print(f"{'─' * 40}")
    
    intel_files = glob.glob(os.path.join(INTEL_DIR, "*.json"))
    
    if not intel_files:
        print(f"❌ No intel files found in {INTEL_DIR}")
        return

    print(f"🔍 Scanning {len(intel_files)} research reports...")
    
    master_list = []
    
    for file_path in sorted(intel_files):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Extract core metadata for the global navigation list
                company_entry = {
                    "company": data.get("company", "Unknown"),
                    "website": data.get("website", ""),
                    "ticker": data.get("ticker", ""),
                    "sector": data.get("sector", ""),
                    "description": data.get("description", ""),
                    # Include the offices so they appear on the global map immediately
                    "offices": data.get("offices", [])
                }
                
                master_list.append(company_entry)
                print(f"  ✓ Registered: {company_entry['company']} ({company_entry['ticker']})")
                
        except Exception as e:
            print(f"  [!] Error processing {os.path.basename(file_path)}: {e}")

    # Write the consolidated file
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(master_list, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Successfully synchronized {len(master_list)} companies.")
    print(f"💾 Updated: {OUTPUT_JSON}")
    print(f"\n🎉 Workflow complete. Run 'npm run dev' to see the updates.\n")

if __name__ == "__main__":
    main()
