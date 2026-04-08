import asyncio
import json
import os
import sys
from dotenv import load_dotenv
import os
import sys

# Load environment variables from .env in the project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from pipeline import research_pipeline

# Ensure we can import from tasks/ and other local files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def run_test_research(query: str):
    """
    Consumes the research_pipeline async generator and prints status updates.
    """
    print(f"\n--- [STARTING RESEARCH: {query}] ---\n")
    
    # Check for TAVILY_API_KEY
    if not os.getenv("TAVILY_API_KEY"):
        print("WARNING: TAVILY_API_KEY not found in environment. Extraction phase will fail.")

    try:
        async for update in research_pipeline(query):
            data = json.loads(update)
            status = data.get("status")
            message = data.get("message")
            
            print(f"[{status.upper()}] {message}")
            
            if status == "completed":
                print("\n--- [REPORT PREVIEW] ---\n")
                report = data.get("report", "")
                print(report[:500] + "...")
                
                # Save to files
                with open("test_report.md", "w") as f:
                    f.write(report)
                
                final_data = data.get("data")
                with open("test_data.json", "w") as f:
                    json.dump(final_data, f, indent=2)
                
                print(f"\n[SUCCESS] Full report saved to test_report.md and test_data.json")
                
                print("\n--- [DATA PREVIEW] ---\n")
                print(json.dumps(final_data, indent=2)[:500] + "...")
            elif status == "error":
                print(f"\nERROR: {data.get('message')}\n")

    except Exception as e:
        print(f"\nFATAL EXCEPTION: {e}\n")

if __name__ == "__main__":
    # Example target for validation
    target_query = "NVIDIA's supply chain in Taiwan and geopolitical risks"
    if len(sys.argv) > 1:
        target_query = " ".join(sys.argv[1:])
    
    asyncio.run(run_test_research(target_query))
