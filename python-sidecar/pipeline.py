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
from typing import AsyncGenerator, Union

from llm import LLMClient
from provider import LLM_OUTPUT_MODE
from schemas import PlannerSchema, SingleTriageSchema, SynthesizerSchema, GeoIntelligenceSchema

logger = logging.getLogger(__name__)

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

        # Scan log files to identify phase boundaries by index.
        import glob, re as _re
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
        for ext_path in glob.glob(os.path.join(log_dir, "*_ExtractorData_output.json")):
            try:
                with open(ext_path) as f:
                    data = json.load(f)
                count = len(data.get("raw_content", []))
                ext_idx = int(_re.search(r"(\d+)", os.path.basename(ext_path)).group(1))
                if _is_enrichment(ext_idx):
                    _io_enrich += count
                else:
                    _io_primary += count
            except Exception:
                pass

        # Count triage evaluations (SingleTriageSchema files — all primary).
        _triage_count = 0
        for tri_path in glob.glob(os.path.join(log_dir, "*_SingleTriageSchema_output.json")):
            _triage_count += 1

        # Count sieve chunks from SynthesizerSchema files.
        _primary_chunks = 0
        _enrich_chunks = 0
        for chunk_path in glob.glob(os.path.join(log_dir, "*_SynthesizerSchema_output.json")):
            chunk_idx = int(_re.search(r"(\d+)", os.path.basename(chunk_path)).group(1))
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
                
    tracker._initial_llm_completed = tracker.llm_completed
    # --------------------------------------------------
    phase_total = 8

    # ------------------------------------------------------------------
    # Shared async multiplexing helpers
    # ------------------------------------------------------------------

    def _drain_queue(q: asyncio.Queue) -> None:
        """Discard any stale items from a queue (non-blocking)."""
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _multiplex(
        generators: dict[str, AsyncGenerator],
        pulse_queue: asyncio.Queue,
    ) -> AsyncGenerator[tuple[str, any], None]:
        """
        Concurrently poll multiple async generators + an LLM progress pulse queue.
        Yields (label, item) tuples. Stops when only llm_pulse remains.
        Cancels all pending tasks on exit.
        """
        pending: dict[asyncio.Task, str] = {}
        for label, gen in generators.items():
            pending[asyncio.create_task(gen.__anext__())] = label
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
                        yield (label, item)
                        if label == "llm_pulse":
                            pending[asyncio.create_task(pulse_queue.get())] = "llm_pulse"
                        else:
                            pending[asyncio.create_task(generators[label].__anext__())] = label
                    except StopAsyncIteration:
                        continue
                    except Exception as e:
                        logger.error("Generator '%s' failed in multiplex: %s", label, e)
                        continue
        finally:
            for task in pending:
                if not task.done():
                    task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

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
        _drain_queue(llm.progress_queue)

        async for label, item in _multiplex({"gen": task_generator}, llm.progress_queue):
            if label == "gen":
                if isinstance(item, ResearchState):
                    state = item
                else:
                    _apply_discovery(item, phase_idx)
                    yield json.dumps(_enrich_progress(item, phase_idx))
            else:  # llm_pulse
                tracker.complete_llm(1, phase_idx)
                pulse = {"status": "synthesizing", "message": "Synthesizing..."}
                yield json.dumps(_enrich_progress(pulse, phase_idx))

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

        _drain_queue(llm.progress_queue)

        generators = {
            "pre": preprocessor_gen,
            "ext": extractor_gen,
        }
        if triage_gen is not None:
            generators["tri"] = triage_gen

        async for label, item in _multiplex(generators, llm.progress_queue):
            if label == "llm_pulse":
                tracker.complete_llm(1, phase_idx)
                pulse = {"status": "synthesizing", "message": "Synthesizing..."}
                yield json.dumps(_enrich_progress(pulse, phase_idx))
            elif isinstance(item, ResearchState):
                state = item
            else:
                _apply_discovery(item, phase_idx)
                yield json.dumps(_enrich_progress(item, phase_idx))

    try:
        # 1. Deterministic Planning
        if state.pipeline_step == "init":
            tracker.start_phase(1, "planning")
            tracker.add_llm_total(tracker.get_llm_multiplier(PlannerSchema), 1)
            yield json.dumps({"status": "planning", "phase_current": 1, "phase_total": phase_total, "message": "Generating research queries...", **tracker.as_dict()})
            state = await run_planner(state)
            tracker.complete_llm(tracker.get_llm_multiplier(PlannerSchema), 1)
            state.pipeline_step = "searching"

        # 2. Search
        if state.pipeline_step == "searching":
            tracker.start_phase(2, "searching")
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
            state.pipeline_step = "extracting"
            tracker.add_llm_total(len(state.search_results) * tracker.get_llm_multiplier(SingleTriageSchema), 3)
            async for update in pipeline_sieve(3, is_enrichment=False): yield update
            state.pipeline_step = "entity_assembly"

        # 5. Entity Assembly (Gap Detection)
        if state.pipeline_step == "entity_assembly":
            tracker.start_phase(4, "assembly")
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
            tracker.add_io_total(len(state.urls), 6)
            async for update in pipeline_sieve(6, is_enrichment=True): yield update
            
            await llm.save_checkpoint("EnrichmentCompleteData", {"status": "enrichment_loop_completed"})

            state.pipeline_step = "drafting"

        # 8. Final Handoff (Parallel Drafting)
        if state.pipeline_step == "drafting":
            tracker.start_phase(7, "drafting")
            async for update in flow(run_drafter(state, llm), 7):
                if "units_discovered" in (u := json.loads(update)):
                    tracker.add_llm_total(u["units_discovered"] * tracker.get_llm_multiplier(), 7)
                    continue
                yield update
            state.pipeline_step = "completed"

        # 9. Delivery
        tracker.start_phase(8, "completed")
        yield json.dumps({
            "status": "completed", 
            "phase_current": 8,
            "phase_total": 8,
            "message": "Research complete.",
            "report": state.final_report_md,
            "data": state.final_report_json,
            **tracker.as_dict()
        })
        
        logger.debug(f"Pipeline finished for: {query}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        yield json.dumps({"status": "error", "message": str(e)})
