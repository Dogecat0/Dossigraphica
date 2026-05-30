import asyncio
import json
import os
import shutil
import sys
import time
import traceback
import signal
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Profiler — streaming debug log + watchdog + interrupt-safe state
# ---------------------------------------------------------------------------

class Profiler:
    """Lightweight streaming profiler for the research pipeline.

    * Writes every event to a debug log file immediately (flush=True).
    * Watchdog timer: if no LLM/IO progress for *stall_seconds*, logs a WARNING.
    * Tracks current task, per-phase timing, and LLM call durations.
    * Safe under Ctrl+C — finalizer flushes and closes the log file.
    """

    def __init__(self, enabled: bool = False, stall_seconds: int = 90):
        self.enabled = enabled
        self.stall_seconds = stall_seconds
        self._log_file = None
        self._last_progress_time = time.monotonic()
        self._current_phase = "init"
        self._current_task = "initializing"
        self._llm_call_id = 0
        self._active_llm_calls: dict[int, float] = {}  # call_id -> start_time
        self._phase_start: dict[str, float] = {}        # phase_name -> start_time
        self._total_llm_duration = 0.0
        self._llm_call_count = 0
        self._watchdog_task = None
        self._shutdown = False

    def open(self, query: str):
        """Open the debug log file (only if enabled). Creates logs/debug/ dir."""
        if not self.enabled:
            return
        log_dir = os.path.join(os.path.dirname(__file__), "logs", "debug")
        os.makedirs(log_dir, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in query)[:80]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(log_dir, f"trace_{ts}_{safe_name}.log")
        self._log_file = open(path, "w", buffering=1)  # line-buffered
        self._write("EVENT", "profiler_start", {"query": query})
        return path

    def close(self):
        """Flush and close the debug log file."""
        self._shutdown = True
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self._log_file:
            self._write("EVENT", "profiler_shutdown", {})
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    # -- Write helpers ------------------------------------------------------

    def _write(self, kind: str, label: str, detail: dict):
        if not self._log_file:
            return
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            line = json.dumps({"t": now, "kind": kind, "label": label, **detail}, default=str)
            self._log_file.write(line + "\n")
        except Exception:
            pass  # don't crash the pipeline over logging

    def log_state(self, data: dict):
        """Log every SSE update from the pipeline (phases, tokens, messages)."""
        if not self._log_file:
            return
        self._last_progress_time = time.monotonic()
        phase = data.get("phase_current", 0)
        status = data.get("status", "?")
        msg = data.get("message", "")
        tokens = data.get("tokens", {})
        self._current_phase = f"p{phase}({status})"
        self._write("PIPELINE", status, {
            "phase": phase,
            "message": msg[:120],
            "token_total": tokens.get("total", 0),
        })

    def log_llm_before(self) -> int:
        """Mark an LLM call starting. Returns a call ID for pairing."""
        if not self._log_file:
            return 0
        self._llm_call_id += 1
        cid = self._llm_call_id
        self._active_llm_calls[cid] = time.monotonic()
        _frame = sys._getframe()
        for _ in range(2):
            if _frame is None:
                break
            _frame = _frame.f_back
        st = "".join(traceback.format_stack(_frame, limit=6)) if _frame else ""
        self._write("LLM_START", f"call_{cid}", {
            "stack": st,
            "phase": self._current_phase,
        })
        return cid

    def log_llm_after(self, call_id: int, tokens: dict | None = None):
        """Mark an LLM call finishing. Logs duration."""
        if not self._log_file or call_id == 0:
            return
        start = self._active_llm_calls.pop(call_id, None)
        if start is None:
            return
        elapsed = time.monotonic() - start
        self._total_llm_duration += elapsed
        self._llm_call_count += 1
        self._write("LLM_END", f"call_{call_id}", {
            "duration_s": round(elapsed, 3),
            "tokens": tokens or {},
            "phase": self._current_phase,
        })

    def log_task(self, label: str, detail: dict | None = None):
        """Log an arbitrary pipeline task event."""
        self._current_task = label
        if not self.enabled:
            return
        if self._log_file:
            self._write("TASK", label, detail or {})

    # -- Watchdog -----------------------------------------------------------

    async def _watchdog_loop(self):
        """Background task: emit a warning if no progress for stall_seconds."""
        try:
            while not self._shutdown:
                await asyncio.sleep(self.stall_seconds)
                elapsed = time.monotonic() - self._last_progress_time
                if elapsed >= self.stall_seconds and self._log_file:
                    self._write("WARN", "STALL_DETECTED", {
                        "idle_seconds": round(elapsed, 1),
                        "phase": self._current_phase,
                        "active_llm_calls": len(self._active_llm_calls),
                        "llm_call_count": self._llm_call_count,
                    })
                    print(
                        f"\n⚠️  STALL WARNING: No progress for {elapsed:.0f}s "
                        f"[phase={self._current_phase}, active_llm={len(self._active_llm_calls)}]"
                    )
        except asyncio.CancelledError:
            pass

    def start_watchdog(self):
        if self.enabled and self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    # -- Reporting ----------------------------------------------------------

    def summary(self) -> dict:
        return {
            "llm_calls": self._llm_call_count,
            "total_llm_duration_s": round(self._total_llm_duration, 3),
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

async def run_test_research(query: str):
    """
    Consumes the research_pipeline async generator and prints status updates with a progress bar.
    Tracks total execution time. DEBUG_PROFILE env var enables a streaming trace log + watchdog.
    Interrupt-safe: Ctrl+C flushes state to disk rather than losing it.
    """

    # -- Log directory cleanup ----------------------------------------------
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
    if os.path.isdir(log_dir):
        log_count = len(os.listdir(log_dir))
        if log_count > 0:
            try:
                choice = input(f"\nLog directory has {log_count} files ({log_dir}). Clean? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"
            if choice in ("", "y", "yes"):
                shutil.rmtree(log_dir)
                os.makedirs(log_dir)
                print(f"  Cleared {log_count} files from log directory.")
            else:
                print("  Keeping existing logs.")

    # -- Reconstruct token_usage.json from checkpoint files ----
    _reconstructed = _reconstruct_token_usage_from_logs(log_dir)
    if _reconstructed is not None:
        _save_token_usage(query, 0.0, _reconstructed, Profiler(enabled=False))

    # -- Init profiler (controlled by DEBUG_PROFILE env var) ----------------
    debug_enabled = os.getenv("DEBUG_PROFILE", "").lower() in ("1", "true", "yes")
    profiler = Profiler(enabled=debug_enabled)
    log_path = profiler.open(query)
    if debug_enabled:
        print(f"  [DEBUG] Trace log → {log_path}")

    print(f"\n--- [STARTING RESEARCH: {query}] ---\n")

    # Check for BRAVE_SEARCH_API_KEY
    if not os.getenv("BRAVE_SEARCH_API_KEY"):
        print("WARNING: BRAVE_SEARCH_API_KEY not found in environment. Search phase will fail.")

    start_time = time.perf_counter()

    # -- Terminal width -----------------------------------------------------
    RESIZE_COOLDOWN = 1.0
    last_seen_cols = None
    resize_last_change = 0.0
    try:
        term_width = os.get_terminal_size().columns
    except OSError:
        term_width = 100

    # -- Snapshot state for interrupt recovery ------------------------------
    _last_completed_data = None  # most recent completed/error data dict
    _interrupted = False
    _saved_files = {}  # path -> bool for audit at shutdown

    # -- Progress bar -------------------------------------------------------
    pbar = tqdm(
        total=100,
        desc="Initializing Research",
        bar_format="{desc} {percentage:3.0f}% | {n_fmt}/{total_fmt} [{elapsed}]{postfix}",
        ncols=term_width,
    )

    # -- Signal handler for graceful Ctrl+C ---------------------------------
    def _handle_sigint(signum, frame):
        nonlocal _interrupted
        if _interrupted:
            print("\n\nForce-exiting…")
            os._exit(1)
        _interrupted = True
        print("\n\n⏳ Interrupt received — saving checkpoint, please wait...")
        pbar.close()
        # Signal all running tasks to cancel
        for task in asyncio.all_tasks():
            task.cancel()

    # Set up signal handler (works because the event loop is on the main thread)
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(_async_interrupt()))

    async def _async_interrupt():
        nonlocal _interrupted
        if _interrupted:
            return
        _interrupted = True
        print("\n\n⏳ Interrupt received — saving checkpoint, please wait...")
        pbar.close()
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()

    # -- Main loop ----------------------------------------------------------
    try:
        profiler.start_watchdog()

        async for update in research_pipeline(query):
            data = json.loads(update)
            status = data.get("status")

            # Log every SSE event to profiler
            profiler.log_state(data)

            # Snapshot the latest pipeline state for recovery
            if status in ("completed", "error"):
                _last_completed_data = data

            # Responsive terminal width with 1s debounce
            now = time.perf_counter()
            try:
                cols = os.get_terminal_size().columns
            except OSError:
                cols = term_width
            if cols != last_seen_cols:
                last_seen_cols = cols
                resize_last_change = now
            if cols != term_width and now - resize_last_change >= RESIZE_COOLDOWN:
                term_width = cols
                pbar.ncols = term_width
            message = data.get("message", "")

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
            llm_line = f"L:{llm_comp:>3}/{llm_total:<3}" if llm_total > 0 else None
            io_line = f"I:{io_comp:>2}/{io_total:<2}" if io_total > 0 else None

            # Token consumption & cost — show input/output/reasoning split
            tokens_data = data.get("tokens", {})
            token_in = tokens_data.get("total_input_tokens", 0)
            token_out = tokens_data.get("total_output_tokens", 0)
            token_reas = tokens_data.get("total_reasoning_tokens", 0)
            token_total = token_in + token_out + token_reas
            token_str = (
                f"T:{token_in // 1000}k/{token_out // 1000}k/{token_reas // 1000}k"
                if token_total > 0 else None
            )
            cost_usd = tokens_data.get("total_cost_usd", 0)
            cost_str = f"${cost_usd:.4f}" if cost_usd > 0 else None

            # Live output token counter: use streaming estimate when mid-call,
            # otherwise real total (output + reasoning).
            est_out = tokens_data.get("streaming_estimated_output", 0)
            est_reas = tokens_data.get("streaming_estimated_reasoning", 0)
            if est_out or est_reas:
                display_out = est_out + est_reas
                out_token_str = f"O~:{display_out:,}"
            else:
                display_out = token_out + token_reas
                out_token_str = f"O:{display_out:,}" if display_out > 0 else None

            eta_str = None
            eta_sec = data.get("eta_seconds")
            if eta_sec is not None:
                m, s = divmod(eta_sec, 60)
                eta_str = f"E:{m:>2}m{s:02d}s" if m > 0 else f"E:{s:>2}s"

            stat_parts = [p for p in [llm_line, io_line, out_token_str, token_str, cost_str, eta_str] if p]
            stats = f"[{' '.join(stat_parts)}]" if stat_parts else ""

            # Phase Roadmap
            p_curr = data.get("phase_current", 0)
            p_total = data.get("phase_total", 0)
            phase_label = f"{p_curr}/{p_total} " if p_total > 0 else ""

            # Message truncated to keep the bar from getting too cramped.
            # The |{bar}| component auto-fills to ncols, but we keep messages
            # short enough that the bar doesn't vanish entirely.
            overhead = 22 + 8 + 30 + len(stats) + 5
            max_msg = max(10, term_width - overhead)
            if len(message) > max_msg:
                message = message[:max_msg - 3] + "..."

            status_label = f"[{phase_label}{status.upper()}]"
            pbar.desc = f"{status_label:<22}"
            pbar.set_postfix_str(f" {stats} {message}")

            # -- Terminal states ------------------------------------------------
            if status == "completed":
                pbar.close()
                end_time = time.perf_counter()
                duration = end_time - start_time

                # Save token usage
                _save_token_usage(query, duration, data.get("tokens", {}), profiler)

                print(f"\n\n--- [RESEARCH FINISHED IN {duration:.2f}s] ---\n")
                print("--- [REPORT PREVIEW] ---\n")
                report = data.get("report", "")
                print(report[:500] + "...")

                with open("test_report.md", "w") as f:
                    f.write(report)
                _saved_files["test_report.md"] = True

                final_data = data.get("data")
                with open("test_data.json", "w") as f:
                    json.dump(final_data, f, indent=2)
                _saved_files["test_data.json"] = True

                cost_usd = tokens_data.get("total_cost_usd", 0)
                prof_summary = profiler.summary()
                cost_str = f", cost: ${cost_usd:.4f}" if cost_usd else ""
                print(f"\n[SUCCESS] Full report saved to test_report.md and test_data.json"
                      f"  | LLM calls: {prof_summary['llm_calls']}, "
                      f"LLM wall time: {prof_summary['total_llm_duration_s']:.1f}s{cost_str}")

            elif status == "error":
                pbar.close()
                print(f"\nERROR: {data.get('message')}\n")

    except (asyncio.CancelledError, KeyboardInterrupt):
        _interrupted = True
        pbar.close()
        elapsed = time.perf_counter() - start_time
        print(f"\n\n--- [INTERRUPTED after {elapsed:.1f}s] ---")

        # Save whatever we have as a partial checkpoint
        if _last_completed_data:
            _save_token_usage_interrupt(query, elapsed, _last_completed_data.get("tokens", {}), profiler)
        else:
            # Even if no completed data, save token usage from the last SSE event
            # (it's captured via profiler, but let's also snapshot from pipeline state)
            _save_token_usage_interrupt(query, elapsed, {}, profiler)

        # Print summary of what was captured
        print("Checkpoint files saved. Pipeline state preserved for resume.")

    except Exception as e:
        pbar.close()
        tb = traceback.format_exc()
        print(f"\nFATAL EXCEPTION: {e}\n{tb}")
        if profiler.enabled:
            profiler._write("FATAL", "exception", {"error": str(e), "traceback": tb})

    finally:
        profiler.close()

        # litellm cleanup with a 30s timeout to prevent hang-on-shutdown
        async def _cleanup_with_timeout():
            try:
                await asyncio.wait_for(close_litellm_async_clients(), timeout=30.0)
            except asyncio.TimeoutError:
                print("  ⚠️  litellm cleanup timed out after 30s (connections may leak)")
            except Exception as e:
                print(f"  ⚠️  litellm cleanup failed: {e}")

        print("\n[SHUTTING DOWN] Closing active connections...")
        await _cleanup_with_timeout()
        print("[CLEANUP COMPLETE]")


# ---------------------------------------------------------------------------
# Standalone helpers for interrupt-safe file writing
# ---------------------------------------------------------------------------

def _save_token_usage(query: str, duration_s: float, tokens_data: dict, profiler: Profiler):
    """Write token_usage.json and log to profiler."""
    path = "token_usage.json"
    cost = tokens_data.get("total_cost_usd", 0)
    record = {
        "query": query,
        "duration_seconds": round(duration_s, 2),
        "estimated_cost_usd": cost,
        "tokens": tokens_data,
        "profiler": profiler.summary(),
    }
    try:
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        print(f"\n[TOKEN USAGE] Saved to {path}")
    except Exception as e:
        print(f"\n[WARN] Failed to save token_usage.json: {e}")


def _save_token_usage_interrupt(query: str, elapsed_s: float, tokens_data: dict, profiler: Profiler):
    """Write a partial checkpoint on interrupt."""
    path = "token_usage.json"
    cost = tokens_data.get("total_cost_usd", 0) if tokens_data else 0
    record = {
        "query": query,
        "duration_seconds": round(elapsed_s, 2),
        "status": "INTERRUPTED",
        "estimated_cost_usd": cost,
        "tokens": tokens_data or {"by_phase": {}},
        "profiler": profiler.summary(),
    }
    try:
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        print(f"\n[CHECKPOINT] Token usage saved to {path}")
    except Exception as e:
        print(f"\n[WARN] Failed to save checkpoint: {e}")

    # Also snapshot the profiler trace path for post-mortem
    print("\n[DEBUG] Trace log preserved for analysis.")


# ---------------------------------------------------------------------------
# Pre-flight: reconstruct token usage from inference logs
# ---------------------------------------------------------------------------

def _reconstruct_token_usage_from_logs(log_dir: str) -> dict | None:
    """Scan all inference log files and reconstruct exact token/cost totals.

    Uses companion ``.meta`` files when available, otherwise reads the saved
    ``_input.md`` / ``_output.json`` and counts tokens via ``litellm.token_counter``.
    Returns a ``tokens`` dict matching ``TaskTracker.as_dict()`` shape, or None.
    """
    import litellm, re
    from provider import ACTIVE_MODEL
    from pipeline import _resolve_cost_rates, _COST_RATES

    if not os.path.isdir(log_dir):
        return None

    # Known LLM-call schema names (not pipeline checkpoints)
    _LLM_SCHEMAS = {
        "SynthesizerSchema", "SingleTriageSchema", "PlannerSchema",
        "OfficeList", "SupplyChainList", "RiskList", "CustomerList",
    }

    total_in = total_out = total_reas = total_cached = total_cw = 0
    files_scanned = 0

    for fname in sorted(os.listdir(log_dir)):
        m = re.match(r"^(\d+)_(.+)_output\.json$", fname)
        if not m:
            continue
        name = m.group(2)
        if name not in _LLM_SCHEMAS:
            continue
        idx = int(m.group(1))

        # Prefer companion .meta file
        meta_path = os.path.join(log_dir, f"{idx:04d}_{name}_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                total_in += meta.get("input_tokens", 0)
                total_out += meta.get("output_tokens", 0)
                total_reas += meta.get("reasoning_tokens", 0)
                total_cached += meta.get("cached_input_tokens", 0)
                total_cw += meta.get("cache_write_tokens", 0)
                files_scanned += 1
                continue
            except Exception:
                pass

        # Fallback: read files and count tokens directly
        out_path = os.path.join(log_dir, fname)
        inp_path = os.path.join(log_dir, f"{idx:04d}_{name}_input.md")

        out_tok = inp_tok = 0
        try:
            with open(out_path) as f:
                out_content = f.read()
            try:
                out_content = json.dumps(json.loads(out_content), separators=(",", ":"))
            except Exception:
                pass
            out_tok = litellm.token_counter(model=ACTIVE_MODEL, text=out_content)
        except Exception:
            pass

        try:
            with open(inp_path) as f:
                inp_content = f.read()
            sys_marker = "## System Prompt\n\n"
            usr_marker = "## User Prompt\n\n"
            sys_start = inp_content.find(sys_marker)
            usr_start = inp_content.find(usr_marker)
            if sys_start >= 0 and usr_start > sys_start:
                sys_text = inp_content[sys_start + len(sys_marker):usr_start]
                if sys_text.endswith("\n"):
                    sys_text = sys_text[:-1]
                usr_text = inp_content[usr_start + len(usr_marker):]
                if usr_text.endswith("\n"):
                    usr_text = usr_text[:-1]
                messages = [
                    {"role": "system", "content": sys_text},
                    {"role": "user", "content": usr_text},
                ]
                inp_tok = litellm.token_counter(model=ACTIVE_MODEL, messages=messages)
            else:
                inp_tok = litellm.token_counter(model=ACTIVE_MODEL, text=inp_content)
        except Exception:
            pass

        total_in += inp_tok
        total_out += out_tok
        files_scanned += 1

    if files_scanned == 0:
        return None

    # Resolve cost rates and compute cost
    _resolve_cost_rates()
    assert _COST_RATES is not None
    inp_rate, out_rate, cache_hit_rate, cache_write_rate = _COST_RATES
    cached_in = min(total_cached, total_in)
    written_in = min(total_cw, total_in - cached_in)
    miss_in = total_in - cached_in - written_in
    cost = miss_in * inp_rate + cached_in * cache_hit_rate + written_in * cache_write_rate + total_out * out_rate

    total_tok = total_in + total_out + total_reas

    return {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_reasoning_tokens": total_reas,
        "total_cached_input_tokens": total_cached,
        "total_cache_write_tokens": total_cw,
        "total": total_tok,
        "total_cost_usd": round(cost, 6),
        "cost_model": _COST_RATES,
        "by_phase": {},
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "NVIDIA's supply chain in Taiwan and geopolitical risks"
    asyncio.run(run_test_research(query))
