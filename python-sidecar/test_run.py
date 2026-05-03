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


from litellm.llms.custom_httpx.async_client_cleanup import (
    close_litellm_async_clients,
    register_async_client_cleanup,
)

# Register atexit handler as a safety net; the explicit await in the finally
# block below is the primary cleanup path.
register_async_client_cleanup()

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
    with tqdm(total=100, desc="Initializing Research", bar_format="{desc} | {n_fmt}/{total_fmt} [{elapsed}, {rate_fmt}{postfix}]") as pbar:
        try:
            async for update in research_pipeline(query):
                data = json.loads(update)
                status = data.get("status")
                message = data.get("message")
                progress = data.get("progress", current_progress)
                
                # Dynamic Total Discovery
                llm_data = data.get("llm", {})
                io_data = data.get("io", {})
                llm_total = llm_data.get("total", 0)
                io_total = io_data.get("total", 0)
                llm_comp = llm_data.get("completed", 0)
                io_comp = io_data.get("completed", 0)
                
                new_total = llm_total + io_total
                new_n = llm_comp + io_comp
                
                # Sync total exactly on resume and throughout
                if new_total > 0 and new_total != pbar.total:
                    pbar.total = new_total
                
                if new_n > pbar.n:
                    pbar.update(new_n - pbar.n)
                
                # Granular absolute reporting
                # Pad numbers to 3 digits for alignment stability
                llm_line = f"L:{llm_comp:>3}/{llm_total:<3}" if llm_total > 0 else " " * 10
                io_line = f"I:{io_comp:>2}/{io_total:<2}" if io_total > 0 else " " * 7
                
                eta_sec = data.get("eta_seconds")
                if eta_sec is not None:
                    m, s = divmod(eta_sec, 60)
                    eta_str = f" E:{m:>2}m{s:>2}s" if m > 0 else f" E:{s:>2}s"
                else:
                    eta_str = " " * 8
                    
                stats = f" [{llm_line} {io_line}{eta_str}]" if llm_line or io_line else ""
                
                # Phase Roadmap
                p_curr = data.get("phase_current", 0)
                p_total = data.get("phase_total", 0)
                phase_label = f"{p_curr}/{p_total} " if p_total > 0 else ""

                # Build a clean, high-density status line
                p_perc = (new_n / new_total * 100) if new_total > 0 else 0
                
                # Truncate message to avoid terminal wrapping
                max_msg = 35
                if len(message) > max_msg:
                    message = message[:max_msg-3] + "..."
                    
                status_label = f"[{phase_label}{status.upper()}]"
                desc = f"{status_label:<30} {p_perc:3.0f}% |{stats} {message}"
                pbar.set_description(desc)
                
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
        finally:
            # Tear down litellm's async HTTP sessions to prevent
            # 'Unclosed client session' / 'coroutine was never awaited' warnings.
            print("\n[SHUTTING DOWN] Closing active connections...")
            await close_litellm_async_clients()
            print("[CLEANUP COMPLETE]")

if __name__ == "__main__":
    # Example target for validation
    target_query = "NVIDIA's supply chain in Taiwan and geopolitical risks"
    if len(sys.argv) > 1:
        target_query = " ".join(sys.argv[1:])
    
    asyncio.run(run_test_research(target_query))
