from schemas import ResearchState
from tasks.planner import run_planner
from tasks.search import run_search
from tasks.source_triage import run_source_triage
from tasks.extractor import run_extractor
from tasks.preprocessor import run_preprocessor
from tasks.entity_assembly import run_entity_assembly
from tasks.drafter import run_drafter
from utils.log_replay import reconstruct_state_from_logs
import logging
import json
import asyncio
import os
import time
from typing import AsyncGenerator, Any, Union

import litellm
from llm import LLMClient
from provider import LLM_OUTPUT_MODE, ACTIVE_MODEL
from schemas import PlannerSchema, SingleTriageSchema, SynthesizerSchema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DEBUG profile helper (mirrors the one in llm.py — opened when DEBUG_PROFILE is set)
# ---------------------------------------------------------------------------
_PIPELINE_DEBUG_FILE = None

def _init_pipeline_debug():
    global _PIPELINE_DEBUG_FILE
    if not os.getenv("DEBUG_PROFILE", "").lower() in ("1", "true", "yes"):
        return
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "debug")
    os.makedirs(log_dir, exist_ok=True)
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"pipeline_trace_{ts}.log")
    _PIPELINE_DEBUG_FILE = open(path, "w", buffering=1)
    _pipeline_debug_write("init", {"msg": "pipeline debug trace opened"})

def _pipeline_debug_write(kind: str, data: dict):
    f = _PIPELINE_DEBUG_FILE
    if f is None:
        return
    try:
        from datetime import datetime as _dt
        import json as _json
        now = _dt.now().isoformat(timespec="milliseconds")
        line = _json.dumps({"t": now, "kind": kind, **data}, default=str)
        f.write(line + "\n")
    except Exception:
        pass

# Initialize on import
_init_pipeline_debug()


def _levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein distance (iterative, O(m*n))."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(dp[j], dp[j - 1], prev)
            prev = temp
    return dp[n]


# ---------------------------------------------------------------------------
# Cost-per-token cache — computed once at first call, then reused
# ---------------------------------------------------------------------------
_COST_RATES: tuple[float, float, float, float] | None = None  # (input_rate, output_rate, cache_hit_rate, cache_write_rate)
_COST_MODEL_SOURCE = None  # human-readable source for the match


def _resolve_cost_rates():
    """Resolve per-token cost rates for ACTIVE_MODEL once, caching the result.

    Returns a 3-tuple: (input_rate, output_rate, cache_hit_input_rate).

    Looks up ``litellm.model_cost`` directly (not ``cost_per_token``) to avoid
    provider-prefix requirements. Strategy:
      1. Exact match on ``ACTIVE_MODEL``.
      2. Bare model name (after ``/``) — works for models like ``gemini-xxx``.
      3. Levenshtein distance against every key in ``litellm.model_cost``.
         Expensive (~200ms) but runs **once** and is cached.
    """
    global _COST_RATES, _COST_MODEL_SOURCE
    if _COST_RATES is not None:
        return

    cost_map = litellm.model_cost
    model = ACTIVE_MODEL

    candidates = [model]
    if "/" in model:
        candidates.append(model.split("/", 1)[1])  # bare name

    # 1-2. Exact matches
    for candidate in candidates:
        entry = cost_map.get(candidate)
        if entry is not None:
            inp = entry.get("input_cost_per_token")
            out = entry.get("output_cost_per_token")
            cache_hit = entry.get("input_cache_hit_cost_per_token", inp)
            cache_write = entry.get("input_cache_write_cost_per_token", inp)
            if inp is not None and out is not None:
                _COST_RATES = (inp, out, cache_hit if cache_hit is not None else inp, cache_write if cache_write is not None else inp)
                _COST_MODEL_SOURCE = f"exact({candidate})"
                logger.debug("Cost rates resolved via exact match: %s", candidate)
                return

    # 3. Levenshtein fallback (one-time)
    raw = model.split("/", 1)[-1]
    logger.info("Fuzzy-matching model '%s' against litellm cost map (%d entries)...",
                raw, len(cost_map))
    best_key = min(cost_map.keys(), key=lambda k: _levenshtein(raw, k))
    best_entry = cost_map[best_key]
    inp = best_entry.get("input_cost_per_token")
    out = best_entry.get("output_cost_per_token")
    cache_hit = best_entry.get("input_cache_hit_cost_per_token", inp)
    cache_write = best_entry.get("input_cache_write_cost_per_token", inp)
    if inp is not None and out is not None:
        _COST_RATES = (inp, out, cache_hit if cache_hit is not None else inp, cache_write if cache_write is not None else inp)
        _COST_MODEL_SOURCE = f"levenshtein({raw} -> {best_key})"
        logger.info("Cost rates resolved via fuzzy match: %s -> %s ($%.2e/$%.2e per token, cache_hit=$%.2e)",
                    raw, best_key, inp, out, _COST_RATES[2])
        return

    _COST_RATES = (0.0, 0.0, 0.0, 0.0)
    _COST_MODEL_SOURCE = "none"
    logger.debug("No cost rates found for %s — cost set to $0", model)


def _compute_llm_cost(input_tokens: int, output_tokens: int, *, cached_input_tokens: int = 0, cache_write_tokens: int = 0, model: str = ACTIVE_MODEL) -> float:
    """Compute estimated LLM cost for a token batch. Uses cached per-token rates.

    Cached input tokens (reads) are billed at ``input_cache_hit_cost_per_token``,
    cache writes at ``input_cache_write_cost_per_token``, and the remainder
    (base / miss) at ``input_cost_per_token``.
    """
    if input_tokens == 0 and output_tokens == 0:
        return 0.0
    _resolve_cost_rates()
    assert _COST_RATES is not None
    inp_rate, out_rate, cache_hit_rate, cache_write_rate = _COST_RATES
    cached_in = min(cached_input_tokens, input_tokens)
    miss_in = input_tokens - cached_in
    return miss_in * inp_rate + cached_in * cache_hit_rate + output_tokens * out_rate


class TaskTracker:
    """Manages absolute task counts and dynamic discovery with per-phase (bracket) timing."""
    def __init__(self):
        self.llm_completed = 0
        self.llm_total = 0
        self.io_completed = 0
        self.io_total = 0
        self._init_time = time.time()
        self._initial_llm_completed = 0
        
        # Per-phase tracking: { phase_idx: {llm_total, llm_completed, start_time} }
        self.phases = {}
        self.active_phase = None

        # Token tracking per phase
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_reasoning_tokens = 0
        self._total_cached_input_tokens = 0
        self._total_cache_write_tokens = 0
        self.phase_input_tokens = {}   # phase_idx -> int
        self.phase_output_tokens = {}  # phase_idx -> int
        self.phase_reasoning_tokens = {}  # phase_idx -> int
        self.phase_cached_input_tokens = {}  # phase_idx -> int
        self.phase_cache_write_tokens = {}  # phase_idx -> int
        # Cost tracking (computed lazily in as_dict)
        self._total_cost = 0.0
        self.phase_cost = {}  # phase_idx -> float

        # Per-call streaming estimates — keyed by call_id so concurrent streams
        # don't trample each other. Each value is (estimated_output, estimated_reasoning).
        self._streaming_estimates: dict[str, tuple[int, int]] = {}
        
    def start_phase(self, idx, name=None):
        self.active_phase = idx
        if idx not in self.phases:
            self.phases[idx] = {
                "name": name,
                "llm_total": 0,
                "llm_completed": 0,
                "io_total": 0,
                "io_completed": 0,
                "start_time": time.time()
            }
        if idx not in self.phase_input_tokens:
            self.phase_input_tokens[idx] = 0
            self.phase_output_tokens[idx] = 0
            self.phase_reasoning_tokens[idx] = 0
            self.phase_cached_input_tokens[idx] = 0
            self.phase_cache_write_tokens[idx] = 0
            self.phase_cost[idx] = 0.0

    def set_streaming_estimates(self, call_id: str, output_tokens: int, reasoning_tokens: int):
        """Set mid-stream token estimates for one call (shown until completion clears it)."""
        if output_tokens > 0 or reasoning_tokens > 0:
            self._streaming_estimates[call_id] = (output_tokens, reasoning_tokens)
        else:
            self._streaming_estimates.pop(call_id, None)

    def clear_streaming_estimate(self, call_id: str):
        """Remove the streaming estimate for a completed call."""
        self._streaming_estimates.pop(call_id, None)

    @property
    def _streaming_estimated_output(self) -> int:
        return sum(v[0] for v in self._streaming_estimates.values())

    @property
    def _streaming_estimated_reasoning(self) -> int:
        return sum(v[1] for v in self._streaming_estimates.values())

    def add_tokens(self, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0, phase_idx=None, cached_input_tokens: int = 0, cache_write_tokens: int = 0, call_id: str | None = None):
        """Track token consumption for an LLM call. Computes cost incrementally.

        Args:
            cached_input_tokens: Input tokens served from the API cache (reads).
            cache_write_tokens:  Input tokens written to the API cache.
            call_id:             If set, removes this call's streaming estimate.

        When exact tokens arrive, any prior streaming estimate is cleared.
        """
        if call_id is not None:
            self.clear_streaming_estimate(call_id)
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_reasoning_tokens += reasoning_tokens
        self._total_cached_input_tokens += cached_input_tokens
        self._total_cache_write_tokens += cache_write_tokens
        target = phase_idx if phase_idx is not None else self.active_phase
        if target is not None:
            if target not in self.phase_input_tokens:
                self.phase_input_tokens[target] = 0
                self.phase_output_tokens[target] = 0
                self.phase_reasoning_tokens[target] = 0
                self.phase_cached_input_tokens[target] = 0
                self.phase_cache_write_tokens[target] = 0
                self.phase_cost[target] = 0.0
            self.phase_input_tokens[target] += input_tokens
            self.phase_output_tokens[target] += output_tokens
            self.phase_reasoning_tokens[target] += reasoning_tokens
            self.phase_cached_input_tokens[target] += cached_input_tokens
            self.phase_cache_write_tokens[target] += cache_write_tokens
            # Incremental cost: reasoning tokens charged as output
            _cost = _compute_llm_cost(input_tokens, output_tokens + reasoning_tokens, cached_input_tokens=cached_input_tokens, cache_write_tokens=cache_write_tokens)
            self._total_cost += _cost
            self.phase_cost[target] += _cost

    def _get_phase(self, idx):
        target = idx if idx is not None else self.active_phase
        if target is not None and target not in self.phases:
            self.start_phase(target)
        return target

    def add_llm_total(self, count, phase_idx=None):
        self.llm_total += count
        target = self._get_phase(phase_idx)
        if target is not None:
            self.phases[target]["llm_total"] += count

    def complete_llm(self, count=1, phase_idx=None):
        self.llm_completed += count
        target = self._get_phase(phase_idx)
        if target is not None:
            self.phases[target]["llm_completed"] += count

    def add_io_total(self, count, phase_idx=None):
        self.io_total += count
        target = self._get_phase(phase_idx)
        if target is not None:
            self.phases[target]["io_total"] += count

    def complete_io(self, count=1, phase_idx=None):
        self.io_completed += count
        target = self._get_phase(phase_idx)
        if target is not None:
            self.phases[target]["io_completed"] += count

    def get_llm_multiplier(self, schema_cls=None) -> int:
        if LLM_OUTPUT_MODE == "one-shot":
            return 1
        if schema_cls:
            return len(schema_cls.model_fields)
        return 2 # default fallback for 2-field schemas like SynthesizerSchema, PlannerSchema

    def as_dict(self):
        elapsed = time.time() - self._init_time
        new_llm = self.llm_completed - self._initial_llm_completed
        
        # 1. Global Rate (Fallback)
        global_rate = elapsed / new_llm if new_llm >= 2 else None
        
        # 2. Segmented ETA Calculation
        # Sum of: (Remaining per Phase * That Phase's Rate) + (Stray remaining * Global Rate)
        total_eta = 0
        units_accounted_for = 0
        has_any_data = False
        
        for idx, p in self.phases.items():
            p_comp = p["llm_completed"]
            p_total = p["llm_total"]
            p_rem = p_total - p_comp
            
            if p_rem > 0:
                p_elapsed = time.time() - p["start_time"]
                if p_comp >= 1:
                    p_rate = p_elapsed / p_comp
                    total_eta += p_rate * p_rem
                    has_any_data = True
                elif global_rate:
                    total_eta += global_rate * p_rem
                    has_any_data = True
            
            units_accounted_for += p_rem

        # Handle any units not in a recorded phase
        stray_rem = (self.llm_total - self.llm_completed) - units_accounted_for
        if stray_rem > 0 and global_rate:
            total_eta += global_rate * stray_rem
            has_any_data = True

        # Build per-phase token breakdown with costs
        tokens_by_phase = {}
        for idx in sorted(self.phases.keys()):
            inp = self.phase_input_tokens.get(idx, 0)
            out = self.phase_output_tokens.get(idx, 0)
            reas = self.phase_reasoning_tokens.get(idx, 0)
            cost = round(self.phase_cost.get(idx, 0.0), 6)
            tokens_by_phase[str(idx)] = {
                "input_tokens": inp,
                "output_tokens": out,
                "reasoning_tokens": reas,
                "total_tokens": inp + out + reas,
                "cost_usd": cost,
            }

        total_tok = self._total_input_tokens + self._total_output_tokens + self._total_reasoning_tokens

        # Ensure cost rates are resolved so cost_model is populated
        _resolve_cost_rates()

        return {
            "llm": {
                "completed": self.llm_completed,
                "total": self.llm_total,
                "remaining": self.llm_total - self.llm_completed
            },
            "io": {
                "completed": self.io_completed,
                "total": self.io_total,
                "remaining": self.io_total - self.io_completed
            },
            "tokens": {
                "total_input": self._total_input_tokens,
                "total_output": self._total_output_tokens,
                "total_reasoning": self._total_reasoning_tokens,
                "total_cached_input": self._total_cached_input_tokens,
                "total_cache_write": self._total_cache_write_tokens,
                "streaming_estimated_output": self._streaming_estimated_output,
                "streaming_estimated_reasoning": self._streaming_estimated_reasoning,
                "total_cost_usd": round(self._total_cost, 6),
                "cost_model": _COST_MODEL_SOURCE or "unknown",
                "total": total_tok,
                "by_phase": tokens_by_phase,
            },
            "elapsed_seconds": int(elapsed),
            "eta_seconds": int(total_eta) if has_any_data else None
        }

async def research_pipeline(query: str) -> AsyncGenerator[str, None]:
    """
    Absolute Unit Dynamic Orchestration Engine.
    No hardcoded progress integers. All work is discovered and tracked as discrete units.
    
    8-Stage Unified Roadmap:
      1: Plan, 2: Search, 3: Triage/Extract/Sieve, 4: Assembly,
      5: Enrich Search, 6: Enrich Extract & Sieve, 7: Draft, 8: Completed.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
    state = reconstruct_state_from_logs(query, log_dir)
    llm = LLMClient()

    tracker = TaskTracker()

    llm.progress_queue = asyncio.Queue()
    
    # --- State Reconstruction for Progress Tracking ---
    # If we resumed past init, we should artificially seed the tracker
    # so the front-end (or test_run.py) correctly displays the massive amount
    # of work that led to this checkpoint rather than starting from 0.
    if state.pipeline_step != "init":
        tracker.start_phase(0, "recovery")

        # --- Snapshot-based recovery ---
        # If a prior run saved a ProgressSnapshotData checkpoint, load it to
        # get exact token/cost totals without scanning any files.
        _snap_loaded = False
        import glob as _glob
        _snap_files = sorted(_glob.glob(os.path.join(log_dir, "*_ProgressSnapshotData_output.json")))
        if _snap_files:
            try:
                with open(_snap_files[-1]) as _sf:
                    _snap = json.load(_sf)
                for _pd in _snap.get("phases", []):
                    _idx = _pd["idx"]
                    if _idx not in tracker.phases:
                        tracker.start_phase(_idx, _pd.get("name"))
                    if _pd.get("llm_total", 0):
                        tracker.add_llm_total(_pd["llm_total"], _idx)
                        tracker.complete_llm(_pd["llm_completed"], _idx)
                    if _pd.get("io_total", 0):
                        tracker.add_io_total(_pd["io_total"], _idx)
                        tracker.complete_io(_pd["io_completed"], _idx)
                    _i = _pd.get("input_tokens", 0)
                    _o = _pd.get("output_tokens", 0)
                    _r = _pd.get("reasoning_tokens", 0)
                    _c = _pd.get("cached_input_tokens", 0)
                    _cw = _pd.get("cache_write_tokens", 0)
                    if _i or _o or _r:
                        tracker.add_tokens(_i, _o, _r, _idx, cached_input_tokens=_c, cache_write_tokens=_cw)
                _snap_loaded = True
                logger.info("Progress snapshot loaded from %s", _snap_files[-1])
            except Exception:
                pass

        if not _snap_loaded:
            # Scan log files to identify phase boundaries by index.
            import re as _re
            _all_logs = []
            if os.path.exists(log_dir):
                for f in os.listdir(log_dir):
                    m = _re.match(r"^(\d+)_(.+)_output\.json$", f)
                    if m:
                        _all_logs.append((int(m.group(1)), m.group(2)))
            _all_logs.sort(key=lambda x: x[0])

            # Find boundary indices for phase separation.
            _assembly_idx = None
            _drafting_idx = None
            for idx, name in _all_logs:
                if "EntityAssemblyData" in name:
                    _assembly_idx = idx
                elif "DraftingCompleteData" in name:
                    _drafting_idx = idx

            def _is_enrichment(fname_idx: int) -> bool:
                return _assembly_idx is not None and fname_idx > _assembly_idx

            # Count IO from ExtractorData file contents (actual fetched URLs).
            _io_primary = 0
            _io_enrich = 0
            for ext_path in _glob.glob(os.path.join(log_dir, "*_ExtractorData_output.json")):
                try:
                    with open(ext_path) as f:
                        data = json.load(f)
                    count = len(data.get("raw_content", []))
                    m = _re.search(r"(\d+)", os.path.basename(ext_path))
                    if m:
                        ext_idx = int(m.group(1))
                        if _is_enrichment(ext_idx):
                            _io_enrich += count
                        else:
                            _io_primary += count
                except Exception:
                    pass

            # Count triage evaluations (SingleTriageSchema files — all primary).
            _triage_count = 0
            for tri_path in _glob.glob(os.path.join(log_dir, "*_SingleTriageSchema_output.json")):
                _triage_count += 1

            # Count sieve chunks from SynthesizerSchema files.
            _primary_chunks = 0
            _enrich_chunks = 0
            for chunk_path in _glob.glob(os.path.join(log_dir, "*_SynthesizerSchema_output.json")):
                m = _re.search(r"(\d+)", os.path.basename(chunk_path))
                if m:
                    chunk_idx = int(m.group(1))
                    if _is_enrichment(chunk_idx):
                        _enrich_chunks += 1
                    else:
                        _primary_chunks += 1

            # Seed all phases, only marking work as completed when the
            # resolved pipeline_step proves it was done in the original run.
            _sieve_mult = tracker.get_llm_multiplier(SynthesizerSchema)

            # Phase 1 — Planner
            tracker.add_llm_total(tracker.get_llm_multiplier(PlannerSchema))
            tracker.complete_llm(tracker.get_llm_multiplier(PlannerSchema))
            # Phase 2 — Search IO
            tracker.add_io_total(1)
            tracker.complete_io(1)
            # Phase 3 — Triage (counted from SingleTriageSchema log files,
            # not from state.search_results which may be overwritten by enrichment SearchData)
            _triage_mult = tracker.get_llm_multiplier(SingleTriageSchema)
            tracker.add_llm_total(_triage_count * _triage_mult)
            tracker.complete_llm(_triage_count * _triage_mult)
            # Phase 3 — Primary sieve chunks
            tracker.add_llm_total(_primary_chunks * _sieve_mult)
            tracker.complete_llm(_primary_chunks * _sieve_mult)
            # Phase 3 — Primary extraction IO
            tracker.add_io_total(_io_primary)
            tracker.complete_io(_io_primary)

            # Phase 4 — Entity assembly (done if we found EntityAssemblyData)
            if _assembly_idx is not None:
                _assembly_calls = 3 * tracker.get_llm_multiplier()
                tracker.add_llm_total(_assembly_calls)
                tracker.complete_llm(_assembly_calls)

            # Phases 5-6 — Enrichment (done if pipeline_step proves it)
            if state.pipeline_step in ["enrichment_searching", "enrichment_extracting", "drafting", "completed"]:
                _enrich_search_io = 1 if (state.enrichment_queries) else 0
                tracker.add_io_total(_enrich_search_io)
                tracker.complete_io(_enrich_search_io)
                tracker.add_llm_total(_enrich_chunks * _sieve_mult)
                tracker.complete_llm(_enrich_chunks * _sieve_mult)
                tracker.add_io_total(_io_enrich)
                tracker.complete_io(_io_enrich)

            # Phase 7 — Drafting (done if DraftingCompleteData checkpoint exists)
            if _drafting_idx is not None:
                _drafting_calls = 13 * tracker.get_llm_multiplier()  # 7 json + 6 md sections
                tracker.add_llm_total(_drafting_calls)
                tracker.complete_llm(_drafting_calls)

            # --- Token recovery from checkpoint files ---
            # Reads exact token counts from companion .meta files (future runs) or
            # reconstructs them from the saved _input.md / _output.json files via
            # litellm.token_counter (existing runs).  This seeds the tracker's
            # token/cost totals so the progress bar is accurate on replays.
            _token_log_dir = log_dir
            for _tok_idx, _tok_name in _all_logs:
                # Determine which phase this call belongs to
                if "PlannerSchema" in _tok_name:
                    _tok_phase = 1
                elif "SingleTriageSchema" in _tok_name:
                    _tok_phase = 3
                elif "SynthesizerSchema" in _tok_name:
                    _tok_phase = 6 if _is_enrichment(_tok_idx) else 3
                elif any(x in _tok_name for x in ("OfficeList", "SupplyChainList", "RiskList", "CustomerList")):
                    _tok_phase = 4
                else:
                    continue  # not an LLM call (SearchData, TriageData, ExtractorData, etc.)

                # Prefer companion .meta file written by the current llm.py (exact counts)
                _meta_path = os.path.join(_token_log_dir, f"{_tok_idx:04d}_{_tok_name}_meta.json")
                if os.path.exists(_meta_path):
                    try:
                        with open(_meta_path) as _mf:
                            _meta = json.load(_mf)
                        tracker.add_tokens(
                            _meta.get("input_tokens", 0),
                            _meta.get("output_tokens", 0),
                            _meta.get("reasoning_tokens", 0),
                            phase_idx=_tok_phase,
                            cached_input_tokens=_meta.get("cached_input_tokens", 0),
                            cache_write_tokens=_meta.get("cache_write_tokens", 0),
                        )
                        continue
                    except Exception:
                        pass

                # Fallback: reconstruct exact counts from the saved files
                _inp_path = os.path.join(_token_log_dir, f"{_tok_idx:04d}_{_tok_name}_input.md")
                _out_path = os.path.join(_token_log_dir, f"{_tok_idx:04d}_{_tok_name}_output.json")
                _in_tok = 0
                _out_tok = 0
                _reas_tok = 0
                try:
                    with open(_out_path) as _of:
                        _out_content = _of.read()
                    # Minify JSON to match the raw response tokens the tracker counted
                    try:
                        _out_content = json.dumps(json.loads(_out_content), separators=(',', ':'))
                    except Exception:
                        pass  # not valid JSON — use as-is
                    _out_tok = litellm.token_counter(model=ACTIVE_MODEL, text=_out_content)
                except Exception:
                    pass
                try:
                    with open(_inp_path) as _if:
                        _inp_content = _if.read()
                    # Reconstruct messages from the _input.md format:
                    #   ## System Prompt\n\n{text}\n\n## User Prompt\n\n{text}
                    _sys_marker = "## System Prompt\n\n"
                    _usr_marker = "## User Prompt\n\n"
                    _sys_start = _inp_content.find(_sys_marker)
                    _usr_start = _inp_content.find(_usr_marker)
                    if _sys_start >= 0 and _usr_start > _sys_start:
                        _sys_text = _inp_content[_sys_start + len(_sys_marker):_usr_start]
                        if _sys_text.endswith('\n'):
                            _sys_text = _sys_text[:-1]
                        _usr_text = _inp_content[_usr_start + len(_usr_marker):]
                        if _usr_text.endswith('\n'):
                            _usr_text = _usr_text[:-1]
                        _messages = [
                            {"role": "system", "content": _sys_text},
                            {"role": "user", "content": _usr_text},
                        ]
                        _in_tok = litellm.token_counter(model=ACTIVE_MODEL, messages=_messages)
                    else:
                        _in_tok = litellm.token_counter(model=ACTIVE_MODEL, text=_inp_content)
                except Exception:
                    pass
                if _in_tok or _out_tok:
                    tracker.add_tokens(_in_tok, _out_tok, _reas_tok, phase_idx=_tok_phase)

            # --- Save progress snapshot for future replays ---
            try:
                _snap_data = {
                    "pipeline_step": state.pipeline_step,
                    "phases": [
                        {
                            "idx": idx,
                            "name": p.get("name"),
                            "llm_total": p["llm_total"],
                            "llm_completed": p["llm_completed"],
                            "io_total": p["io_total"],
                            "io_completed": p["io_completed"],
                            "input_tokens": tracker.phase_input_tokens.get(idx, 0),
                            "output_tokens": tracker.phase_output_tokens.get(idx, 0),
                            "reasoning_tokens": tracker.phase_reasoning_tokens.get(idx, 0),
                            "cached_input_tokens": tracker.phase_cached_input_tokens.get(idx, 0),
                            "cache_write_tokens": tracker.phase_cache_write_tokens.get(idx, 0),
                        }
                        for idx, p in sorted(tracker.phases.items())
                    ],
                    "total_input_tokens": tracker._total_input_tokens,
                    "total_output_tokens": tracker._total_output_tokens,
                    "total_reasoning_tokens": tracker._total_reasoning_tokens,
                    "total_cached_input_tokens": tracker._total_cached_input_tokens,
                    "total_cache_write_tokens": tracker._total_cache_write_tokens,
                    "total_cost": tracker._total_cost,
                }
                await llm.save_checkpoint("ProgressSnapshotData", _snap_data)
            except Exception:
                pass
    tracker._initial_llm_completed = tracker.llm_completed
    # --------------------------------------------------
    phase_total = 8

    # ------------------------------------------------------------------
    # Shared async multiplexing helpers
    # ------------------------------------------------------------------

    def _drain_queue(q: asyncio.Queue | None) -> None:
        """Discard any stale items from a queue (non-blocking)."""
        if q is None:
            return
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _multiplex(
        generators: dict[str, AsyncGenerator],
        pulse_queue: asyncio.Queue | None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """
        Concurrently poll multiple async generators.
        When *pulse_queue* is provided, also polls it for LLM progress pulses.
        Yields (label, item) tuples. Stops when only llm_pulse remains.
        Cancels all pending tasks on exit.
        """
        _mx_start = time.monotonic()
        pending: dict[asyncio.Task, str] = {}
        for label, gen in generators.items():
            pending[asyncio.create_task(gen.__anext__())] = label
        if pulse_queue is not None:
            pending[asyncio.create_task(pulse_queue.get())] = "llm_pulse"

        try:
            while pending:
                if len(pending) == 1 and "llm_pulse" in pending.values():
                    break

                done, _ = await asyncio.wait(pending.keys(), return_when=asyncio.FIRST_COMPLETED)
                for future in done:
                    label = pending.pop(future)
                    try:
                        item = future.result()
                        # Sentinel from pulser: no more pulses will arrive, so
                        # don't re-create the pulse task.  The break condition
                        # at the top of the loop will fire once generators exhaust.
                        if label == "llm_pulse" and item is None:
                            continue
                        yield (label, item)
                        if label == "llm_pulse" and pulse_queue is not None:
                            pending[asyncio.create_task(pulse_queue.get())] = "llm_pulse"
                        else:
                            pending[asyncio.create_task(generators[label].__anext__())] = label
                    except StopAsyncIteration:
                        continue
                    except Exception as e:
                        logger.error("Generator '%s' failed in multiplex: %s", label, e)
                        continue
        finally:
            _cancel_start = time.monotonic()
            for task in pending:
                if not task.done():
                    task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            _cancel_dur = time.monotonic() - _cancel_start
            if _cancel_dur > 2.0:
                logger.warning(
                    "Multiplex cleanup took %.1fs to cancel %d pending tasks",
                    _cancel_dur, len(pending),
                )
            _pipeline_debug_write("multiplex_end", {
                "total_s": round(time.monotonic() - _mx_start, 3),
                "cancel_s": round(_cancel_dur, 3),
            })

    def _apply_discovery(update: dict, phase_idx: int) -> None:
        """Apply discovery pulses (units_discovered) to the tracker."""
        if "units_discovered" in update:
            disc_type = update.get("unit_type", "llm")
            if disc_type == "llm":
                tracker.add_llm_total(
                    update["units_discovered"] * tracker.get_llm_multiplier(), phase_idx,
                )
            elif disc_type == "io":
                tracker.add_io_total(update["units_discovered"], phase_idx)
        else:
            unit_type = update.get("unit", "None")
            if unit_type == "llm":
                tracker.complete_llm(1, phase_idx)
            elif unit_type == "io":
                tracker.complete_io(1, phase_idx)

    def _apply_llm_pulse(pulse: dict, phase_idx: int) -> None:
        """Apply an LLM progress pulse to the tracker.

        Two pulse types:
          - ``{"type": "stream_estimate", "call_id": "…", "estimated_output_tokens": N, "estimated_reasoning_tokens": M}``
            → live mid-stream estimate (no completion count increment).
          - ``{"call_id": "…", "tokens": {…}}`` → exact completion pulse.
        """
        call_id = pulse.get("call_id", "")
        if pulse.get("type") == "stream_estimate":
            # Read the LATEST estimate from the in-place dict (the queued wakeup
            # may be stale — the real value was updated since it was pushed).
            _latest = llm._latest_stream_pulses.get(call_id, pulse)
            _est_out = _latest.get("estimated_output_tokens", 0)
            _est_reas = _latest.get("estimated_reasoning_tokens", 0)
            tracker.set_streaming_estimates(call_id, _est_out, _est_reas)
            return
        token_data = pulse.get("tokens", {})
        if not isinstance(token_data, dict):
            logger.error("llm_pulse tokens is not a dict: %s (type=%s)", token_data, type(token_data).__name__)
            tracker.complete_llm(1, phase_idx)
            return
        input_t = token_data.get("input", 0)
        output_t = token_data.get("output", 0)
        reasoning_t = token_data.get("reasoning", 0)
        cached_t = token_data.get("cached_input", 0)
        cache_write_t = token_data.get("cache_write", 0)
        if input_t > 0 or output_t > 0 or reasoning_t > 0:
            try:
                tracker.add_tokens(input_t, output_t, reasoning_t, phase_idx, cached_input_tokens=cached_t, cache_write_tokens=cache_write_t, call_id=call_id)
            except Exception as _add_tok_err:
                logger.error("add_tokens failed: %s %s", type(_add_tok_err).__name__, _add_tok_err)
        try:
            tracker.complete_llm(1, phase_idx)
        except Exception as _comp_err:
            logger.error("complete_llm failed: %s %s", type(_comp_err).__name__, _comp_err)

    def _enrich_progress(item: dict, phase_idx: int) -> dict:
        """Attach progress metadata to a status update dict."""
        item.update(tracker.as_dict())
        item.update({"phase_current": phase_idx, "phase_total": phase_total})
        return item

    # ------------------------------------------------------------------
    # flow: multiplex a single task generator with LLM pulse queue
    # ------------------------------------------------------------------

    async def flow(
        task_generator: AsyncGenerator[Union[dict, ResearchState], None], phase_idx: int,
    ) -> AsyncGenerator[str, None]:
        nonlocal state
        _pq = llm.progress_queue
        assert _pq is not None
        _drain_queue(_pq)

        async for label, item in _multiplex({"gen": task_generator}, _pq):
            if label == "gen":
                if isinstance(item, ResearchState):
                    state = item
                else:
                    _apply_discovery(item, phase_idx)
                    yield json.dumps(_enrich_progress(item, phase_idx))
            else:  # llm_pulse — tracker update only, no SSE yield
                _apply_llm_pulse(item, phase_idx)

    # ------------------------------------------------------------------
    # pipeline_sieve: multiplex extractor + preprocessor (+ optional triage)
    # ------------------------------------------------------------------

    async def pipeline_sieve(phase_idx: int, is_enrichment: bool = False) -> AsyncGenerator[str, None]:
        nonlocal state
        triage_to_extract_queue = asyncio.Queue()
        extract_to_pre_queue = asyncio.Queue()

        preprocessor_gen = run_preprocessor(state, extract_to_pre_queue, llm)

        if not is_enrichment:
            triage_gen = run_source_triage(state, triage_to_extract_queue, llm)
            extractor_gen = run_extractor(state, extract_to_pre_queue, triage_to_extract_queue)
        else:
            triage_gen = None
            extractor_gen = run_extractor(state, extract_to_pre_queue, None)

        _pq = llm.progress_queue
        assert _pq is not None
        _drain_queue(_pq)

        generators = {
            "pre": preprocessor_gen,
            "ext": extractor_gen,
        }
        if triage_gen is not None:
            generators["tri"] = triage_gen

        _pipeline_debug_write("sieve_start", {
            "phase": phase_idx,
            "is_enrichment": is_enrichment,
            "generators": list(generators.keys()),
        })

        _sieve_event_count = 0
        _last_rate_event = 0
        _last_rate_time = 0.0
        async for label, item in _multiplex(generators, _pq):
            _sieve_event_count += 1

            # Log queue depths every 100 events
            if _sieve_event_count % 100 == 0:
                _now = time.monotonic()
                _rate = (_sieve_event_count - _last_rate_event) / (_now - _last_rate_time) if _last_rate_event and _last_rate_time > 0 else 0.0
                _pipeline_debug_write("queue_depth", {
                    "phase": phase_idx,
                    "triage_to_extract": triage_to_extract_queue.qsize(),
                    "extract_to_pre": extract_to_pre_queue.qsize(),
                    "llm_pq": _pq.qsize(),
                    "event_count": _sieve_event_count,
                    "event_rate": round(_rate, 1),
                })
                _last_rate_event = _sieve_event_count
                _last_rate_time = _now

            try:
                if label == "llm_pulse":
                    _apply_llm_pulse(item, phase_idx)
                elif isinstance(item, ResearchState):
                    state = item
                else:
                    _apply_discovery(item, phase_idx)
                    yield json.dumps(_enrich_progress(item, phase_idx))
            except Exception as _sieve_item_err:
                import traceback as _tb
                _tb_str = "".join(_tb.format_exception_only(type(_sieve_item_err), _sieve_item_err)).strip()
                logger.error(
                    "Sieve item processing failed (label=%s, item_type=%s): %s | %s",
                    label, type(item).__name__, _sieve_item_err, _tb_str,
                )

        _pipeline_debug_write("sieve_end", {
            "phase": phase_idx,
            "total_events": _sieve_event_count,
        })

    try:
        # 1. Deterministic Planning
        if state.pipeline_step == "init":
            tracker.start_phase(1, "planning")
            _pipeline_debug_write("phase_start", {"phase": 1, "name": "planning", "step": state.pipeline_step})
            tracker.add_llm_total(tracker.get_llm_multiplier(PlannerSchema), 1)
            yield json.dumps({"status": "planning", "phase_current": 1, "phase_total": phase_total, "message": "Generating research queries...", **tracker.as_dict()})
            state = await run_planner(state)
            tracker.complete_llm(tracker.get_llm_multiplier(PlannerSchema), 1)
            state.pipeline_step = "searching"

        # 2. Search
        if state.pipeline_step == "searching":
            tracker.start_phase(2, "searching")
            _pipeline_debug_write("phase_start", {"phase": 2, "name": "searching", "step": state.pipeline_step})
            tracker.add_io_total(1, 2)
            yield json.dumps({
                "status": "searching", 
                "phase_current": 2, 
                "phase_total": phase_total, 
                "message": f"Executing {len(state.search_queries)} search queries...",
                "queries": state.search_queries,
                **tracker.as_dict()
            })
            state = await run_search(state)
            tracker.complete_io(1, 2)
            state.pipeline_step = "source_triage"
        
        # 3. Triage & Managed Extraction & Sieve (Overlapped)
        if state.pipeline_step == "source_triage" or state.pipeline_step == "extracting":
            tracker.start_phase(3, "extracting")
            _pipeline_debug_write("phase_start", {"phase": 3, "name": "extracting", "step": state.pipeline_step, "search_results": len(state.search_results)})
            state.pipeline_step = "extracting"
            tracker.add_llm_total(len(state.search_results) * tracker.get_llm_multiplier(SingleTriageSchema), 3)
            async for update in pipeline_sieve(3, is_enrichment=False): yield update
            state.pipeline_step = "entity_assembly"

        # 5. Entity Assembly (Gap Detection)
        if state.pipeline_step == "entity_assembly":
            tracker.start_phase(4, "assembly")
            _pipeline_debug_write("phase_start", {"phase": 4, "name": "assembly", "step": state.pipeline_step, "facts": len(state.extracted_facts)})
            yield json.dumps({
                "status": "entity_assembly", 
                "phase_current": 4, 
                "phase_total": phase_total, 
                "message": "Pre-assembling entities to detect geographic data gaps...", 
                **tracker.as_dict()
            })
            state = await run_entity_assembly(state, llm)
            if state.enrichment_queries:
                state.pipeline_step = "enrichment_searching"
            else:
                logger.debug("No geographic gaps detected. Skipping enrichment loop.")
                state.pipeline_step = "drafting"

        # 6. Enrichment Search
        if state.pipeline_step == "enrichment_searching":
            tracker.start_phase(5, "enrichment_searching")
            _pipeline_debug_write("phase_start", {"phase": 5, "name": "enrichment_searching", "step": state.pipeline_step, "queries": len(state.enrichment_queries)})
            tracker.add_io_total(1, 5)
            yield json.dumps({
                "status": "enrichment_searching", 
                "phase_current": 5, 
                "phase_total": phase_total, 
                "message": f"Running {len(state.enrichment_queries)} targeted enrichment searches...", 
                **tracker.as_dict()
            })
            state.search_queries = state.enrichment_queries
            state = await run_search(state)
            tracker.complete_io(1, 5)
            state.pipeline_step = "enrichment_extracting"

        # 7. Enrichment Extract & Sieve
        if state.pipeline_step == "enrichment_extracting":
            tracker.start_phase(6, "enrichment_extracting")
            _pipeline_debug_write("phase_start", {"phase": 6, "name": "enrichment_extracting", "step": state.pipeline_step, "urls": len(state.urls)})
            tracker.add_io_total(len(state.urls), 6)
            async for update in pipeline_sieve(6, is_enrichment=True): yield update
            
            await llm.save_checkpoint("EnrichmentCompleteData", {"status": "enrichment_loop_completed"})

            state.pipeline_step = "drafting"

        # 8. Final Handoff (Parallel Drafting)
        if state.pipeline_step == "drafting":
            tracker.start_phase(7, "drafting")
            _pipeline_debug_write("phase_start", {"phase": 7, "name": "drafting", "step": state.pipeline_step, "facts": len(state.extracted_facts)})
            async for update in flow(run_drafter(state, llm), 7):
                if "units_discovered" in (u := json.loads(update)):
                    tracker.add_llm_total(u["units_discovered"] * tracker.get_llm_multiplier(), 7)
                    continue
                yield update
            state.pipeline_step = "completed"

        # 9. Delivery
        tracker.start_phase(8, "completed")
        _pipeline_debug_write("phase_start", {"phase": 8, "name": "completed", "step": state.pipeline_step})
        yield json.dumps({
            "status": "completed", 
            "phase_current": 8,
            "phase_total": 8,
            "message": "Research complete.",
            "report": state.final_report_md,
            "data": state.final_report_json,
            **tracker.as_dict()
        })

        # Save final progress snapshot for future replays
        try:
            _snap_data = {
                "pipeline_step": "completed",
                "phases": [
                    {
                        "idx": idx,
                        "name": p.get("name"),
                        "llm_total": p["llm_total"],
                        "llm_completed": p["llm_completed"],
                        "io_total": p["io_total"],
                        "io_completed": p["io_completed"],
                        "input_tokens": tracker.phase_input_tokens.get(idx, 0),
                        "output_tokens": tracker.phase_output_tokens.get(idx, 0),
                        "reasoning_tokens": tracker.phase_reasoning_tokens.get(idx, 0),
                        "cached_input_tokens": tracker.phase_cached_input_tokens.get(idx, 0),
                            "cache_write_tokens": tracker.phase_cache_write_tokens.get(idx, 0),
                    }
                    for idx, p in sorted(tracker.phases.items())
                ],
                "total_input_tokens": tracker._total_input_tokens,
                "total_output_tokens": tracker._total_output_tokens,
                "total_reasoning_tokens": tracker._total_reasoning_tokens,
                "total_cached_input_tokens": tracker._total_cached_input_tokens,
                    "total_cache_write_tokens": tracker._total_cache_write_tokens,
                "total_cost": tracker._total_cost,
            }
            await llm.save_checkpoint("ProgressSnapshotData", _snap_data)
        except Exception:
            pass
        
        logger.debug(f"Pipeline finished for: {query}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        yield json.dumps({"status": "error", "message": str(e)})
