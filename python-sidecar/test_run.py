import asyncio
import json
import os
import sys
import time
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables from .env in the project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from pipeline import research_pipeline

# Ensure we can import from tasks/ and other local files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def run_test_research(query: str):
    """
    Consumes the research_pipeline async generator and prints status updates with a progress bar.
    Tracks total execution time.
    """
    print(f"\n--- [STARTING RESEARCH: {query}] ---\n")
    
    # Check for BRAVE_SEARCH_API_KEY
    if not os.getenv("BRAVE_SEARCH_API_KEY"):
        print("WARNING: BRAVE_SEARCH_API_KEY not found in environment. Search phase will fail.")

    start_time = time.perf_counter()
    current_progress = 0
    with tqdm(total=100, desc="Initializing Research", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]") as pbar:
        try:
            async for update in research_pipeline(query):
                data = json.loads(update)
                status = data.get("status")
                message = data.get("message")
                progress = data.get("progress", current_progress)
                
                # Update progress bar
                if progress > current_progress:
                    pbar.update(progress - current_progress)
                    current_progress = progress
                
                pbar.set_description(f"[{status.upper()}] {message}")
                
                if status == "completed":
                    pbar.close()
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    
                    print(f"\n\n--- [RESEARCH FINISHED IN {duration:.2f}s] ---\n")
                    print("--- [REPORT PREVIEW] ---\n")
                    report = data.get("report", "")
                    print(report[:500] + "...")
                    
                    # Save to files
                    with open("test_report.md", "w") as f:
                        f.write(report)
                    
                    final_data = data.get("data")
                    with open("test_data.json", "w") as f:
                        json.dump(final_data, f, indent=2)
                    
                    print(f"\n[SUCCESS] Full report saved to test_report.md and test_data.json")
                
                elif status == "error":
                    pbar.close()
                    print(f"\nERROR: {data.get('message')}\n")

        except Exception as e:
            pbar.close()
            print(f"\nFATAL EXCEPTION: {e}\n")

if __name__ == "__main__":
    # Example target for validation
    target_query = "NVIDIA's supply chain in Taiwan and geopolitical risks"
    if len(sys.argv) > 1:
        target_query = " ".join(sys.argv[1:])
    
    asyncio.run(run_test_research(target_query))
