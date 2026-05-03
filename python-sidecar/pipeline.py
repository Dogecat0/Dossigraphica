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

from llm import LLM_OUTPUT_MODE
from schemas import PlannerSchema, SingleTriageSchema, SynthesizerSchema, GeoIntelligenceSchema

logger = logging.getLogger(__name__)

class TaskTracker:
    """Manages absolute task counts and dynamic discovery."""
    def __init__(self):
        self.llm_completed = 0
        self.llm_total = 0
        self.io_completed = 0
        self.io_total = 0
        self._init_time = time.time()
        self._initial_llm_completed = 0
        
    def get_llm_multiplier(self, schema_cls=None) -> int:
        if LLM_OUTPUT_MODE == "one-shot":
            return 1
        if schema_cls:
            return len(schema_cls.model_fields)
        return 2 # default fallback for 2-field schemas like SynthesizerSchema, PlannerSchema

    def as_dict(self):
        new_llm = self.llm_completed - self._initial_llm_completed
        elapsed = time.time() - self._init_time
        
        eta_seconds = None
        # Require a tiny sample size of 2 completions before guessing ETA to avoid wild initial swings
        if new_llm >= 2:
            rate = elapsed / new_llm
            eta_seconds = int(rate * (self.llm_total - self.llm_completed))

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
            "eta_seconds": eta_seconds
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
    
    tracker = TaskTracker()
    
    from llm import llm
    llm.progress_queue = asyncio.Queue()
    
    # --- State Reconstruction for Progress Tracking ---
    # If we resumed past init, we should artificially seed the tracker
    # so the front-end (or test_run.py) correctly displays the massive amount
    # of work that led to this checkpoint rather than starting from 0.
    if state.pipeline_step != "init":
        tracker.llm_total += tracker.get_llm_multiplier(PlannerSchema) ; tracker.llm_completed += tracker.get_llm_multiplier(PlannerSchema) # Planner
        tracker.io_total += 1 ; tracker.io_completed += 1 # Primary Search
        
        triage_multiplier = tracker.get_llm_multiplier(SingleTriageSchema)
        tracker.llm_total += len(state.search_results) * triage_multiplier
        tracker.llm_completed += len(state.search_results) * triage_multiplier # Triage
        
        # Determine how many Extraction and Preprocessing chunks succeeded 
        # by simply counting what exists in the logs director
        if os.path.exists(log_dir):
            import glob
            chunk_files = glob.glob(os.path.join(log_dir, "*_SynthesizerSchema_output.json"))
            num_chunks = len(chunk_files)
            sieve_multiplier = tracker.get_llm_multiplier(SynthesizerSchema)
            tracker.llm_total += num_chunks * sieve_multiplier ; tracker.llm_completed += num_chunks * sieve_multiplier # Sieve
            
            # Count the Extractor data to approximate IO steps
            ext_files = glob.glob(os.path.join(log_dir, "*_ExtractorData_output.json"))
            if ext_files:
                approx_io = len(state.urls) 
                tracker.io_total += approx_io ; tracker.io_completed += approx_io
                
        if state.pipeline_step in ["enrichment_searching", "enrichment_extracting", "drafting"]:
            assembly_calls = 3 * tracker.get_llm_multiplier() # Assuming Assembly uses ~2 field schemas
            tracker.llm_total += assembly_calls ; tracker.llm_completed += assembly_calls # Entity assembly
            
            if hasattr(state, "enrichment_queries") and state.enrichment_queries:
                tracker.io_total += 1 ; tracker.io_completed += 1 # Enrichment Search
                
    tracker._initial_llm_completed = tracker.llm_completed
    # --------------------------------------------------
    phase_total = 8

    async def flow(task_generator: AsyncGenerator[Union[dict, ResearchState], None], phase_idx: int) -> AsyncGenerator[str, None]:
        """Helper to stream granular units and capture the final state."""
        nonlocal state
        
        # Multiplex between task generator and global LLM pulse queue
        gen_iter = task_generator.__aiter__()
        
        while not llm.progress_queue.empty():
            try:
                llm.progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        pending = {
            asyncio.create_task(gen_iter.__anext__()): "gen",
            asyncio.create_task(llm.progress_queue.get()): "llm_pulse"
        }
        
        try:
            while pending:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for future in done:
                    label = pending.pop(future)
                    try:
                        item = future.result()
                        
                        if label == "gen":
                            if isinstance(item, ResearchState):
                                state = item
                            else:
                                # Discovery pulse handling
                                if "units_discovered" in item:
                                    disc_type = item.get("unit_type", "llm")
                                    if disc_type == "llm":
                                        tracker.llm_total += item["units_discovered"] * tracker.get_llm_multiplier()
                                    elif disc_type == "io":
                                        tracker.io_total += item["units_discovered"]
                                else:
                                    unit_type = item.get("unit", "None")
                                    if unit_type == "io": tracker.io_completed += 1
                                    # Note: 'llm' unit is ignored here as it's handled by 'llm_pulse' label
                                
                                item.update(tracker.as_dict())
                                item.update({"phase_current": phase_idx, "phase_total": phase_total})
                                yield json.dumps(item)
                            
                            # Keep polling generator
                            pending[asyncio.create_task(gen_iter.__anext__())] = "gen"
                            
                        elif label == "llm_pulse":
                            tracker.llm_completed += 1
                            update = {"status": "synthesizing", "message": "Synthesizing..."}
                            update.update(tracker.as_dict())
                            update.update({"phase_current": phase_idx, "phase_total": phase_total})
                            yield json.dumps(update)
                            
                            # Keep polling pulse queue
                            pending[asyncio.create_task(llm.progress_queue.get())] = "llm_pulse"
                            
                    except StopAsyncIteration:
                        continue
                    except Exception as e:
                        if label != "llm_pulse": # Pulse queue shouldn't fail, but generator might
                            logger.error(f"Error in flow phase {phase_idx} ({label}): {e}")
                        continue
        finally:
            # Interrupt Trap: Cancel all inflight requests
            for task in pending:
                if not task.done():
                    task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def pipeline_sieve(phase_idx: int, is_enrichment: bool = False) -> AsyncGenerator[str, None]:
        """Manages the parallel execution of extraction and preprocessing."""
        nonlocal state
        triage_to_extract_queue = asyncio.Queue()
        extract_to_pre_queue = asyncio.Queue()
        
        # Start the generators
        preprocessor_gen = run_preprocessor(state, extract_to_pre_queue)
        
        if not is_enrichment:
            triage_gen = run_source_triage(state, triage_to_extract_queue)
            extractor_gen = run_extractor(state, extract_to_pre_queue, triage_to_extract_queue)
        else:
            triage_gen = None
            extractor_gen = run_extractor(state, extract_to_pre_queue)

        # Helper to consume a generator and push to a unified queue
        async def wrap_gen(gen, suffix_sentinel=False):
            async for update in gen:
                if isinstance(update, ResearchState):
                    pass # We'll get the final state from the aggregate
                else:
                    yield update
            if suffix_sentinel:
                await queue.put(None)

        # Merge generators manually
        # Note: We need to pull from BOTH concurrently.
        # However, preprocessor_gen won't finish until extractor_gen puts the sentinel.
        
        # Drain any stale pulses from previous serial phases
        while not llm.progress_queue.empty():
            try:
                llm.progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        # Capture updates and yield them
        ext_iter = extractor_gen.__aiter__()
        pre_iter = preprocessor_gen.__aiter__()
        
        # Use a task-based approach to pull from generators
        pending = {
            asyncio.create_task(preprocessor_gen.__anext__()): "pre",
            asyncio.create_task(extractor_gen.__anext__()): "ext",
            asyncio.create_task(llm.progress_queue.get()): "llm_pulse"
        }
        if triage_gen is not None:
            pending[asyncio.create_task(triage_gen.__anext__())] = "tri"

        try:
            while pending:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for future in done:
                    label = pending.pop(future)
                    try:
                        update = future.result()
                        
                        if label == "llm_pulse":
                            tracker.llm_completed += 1
                            update = {"status": "synthesizing", "message": "Synthesizing..."}
                        elif isinstance(update, ResearchState):
                            state = update
                            # Re-poll based on label
                            if label == "ext":
                                pending[asyncio.create_task(extractor_gen.__anext__())] = "ext"
                            elif label == "pre":
                                pending[asyncio.create_task(preprocessor_gen.__anext__())] = "pre"
                            elif label == "tri" and triage_gen is not None:
                                pending[asyncio.create_task(triage_gen.__anext__())] = "tri"
                            continue
                        else:
                            # Discovery pulse handling: Preprocessor discovered units
                            if "units_discovered" in update:
                                disc_type = update.get("unit_type", "llm")
                                if disc_type == "llm":
                                    tracker.llm_total += update["units_discovered"] * tracker.get_llm_multiplier()
                                elif disc_type == "io":
                                    tracker.io_total += update["units_discovered"]
                            else:
                                unit_type = update.get("unit", "None")
                                if unit_type == "llm": tracker.llm_completed += 1
                                elif unit_type == "io": tracker.io_completed += 1
                        
                        update.update(tracker.as_dict())
                        update.update({"phase_current": phase_idx, "phase_total": phase_total})
                        yield json.dumps(update)
                        
                        # Keep polling the same generator/queue
                        if label == "ext":
                            pending[asyncio.create_task(extractor_gen.__anext__())] = "ext"
                        elif label == "pre":
                            pending[asyncio.create_task(preprocessor_gen.__anext__())] = "pre"
                        elif label == "tri" and triage_gen is not None:
                            pending[asyncio.create_task(triage_gen.__anext__())] = "tri"
                        elif label == "llm_pulse":
                            pending[asyncio.create_task(llm.progress_queue.get())] = "llm_pulse"
                            
                    except StopAsyncIteration:
                        # Generator finished naturally, no need to push sentinel here because
                        # triage -> extractor -> preprocessor push their own queue sentinels.
                        continue
                    except Exception as e:
                        logger.error(f"Error in parallel phase {phase_idx} ({label}): {e}")
                        continue
        finally:
            # Interrupt Trap: Cancel all inflight requests
            for task in pending:
                if not task.done():
                    task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    try:
        # 1. Deterministic Planning
        if state.pipeline_step == "init":
            tracker.llm_total += tracker.get_llm_multiplier(PlannerSchema)
            yield json.dumps({"status": "planning", "phase_current": 1, "phase_total": 9, "message": "Generating research queries...", **tracker.as_dict()})
            state = await run_planner(state)
            tracker.llm_completed += tracker.get_llm_multiplier(PlannerSchema)
            state.pipeline_step = "searching"

        # 2. Search (Brave Discovery)
        if state.pipeline_step == "searching":
            tracker.io_total += 1
            yield json.dumps({
                "status": "searching", 
                "phase_current": 2, 
                "phase_total": 9, 
                "message": f"Executing {len(state.search_queries)} search queries via Brave Discovery...",
                "queries": state.search_queries,
                **tracker.as_dict()
            })
            state = await run_search(state)
            tracker.io_completed += 1
            state.pipeline_step = "source_triage"
        
        # 3. Triage & Managed Extraction & Sieve (Overlapped)
        if state.pipeline_step == "source_triage" or state.pipeline_step == "extracting":
            state.pipeline_step = "extracting"
            tracker.llm_total += len(state.search_results) * tracker.get_llm_multiplier(SingleTriageSchema)
            async for update in pipeline_sieve(3, is_enrichment=False): yield update
            state.pipeline_step = "entity_assembly"

        # 5. Entity Assembly (Gap Detection)
        if state.pipeline_step == "entity_assembly":
            yield json.dumps({
                "status": "entity_assembly", 
                "phase_current": 4, 
                "phase_total": 8, 
                "message": "Pre-assembling entities to detect geographic data gaps...", 
                **tracker.as_dict()
            })
            state = await run_entity_assembly(state)
            if state.enrichment_queries:
                state.pipeline_step = "enrichment_searching"
            else:
                logger.debug("No geographic gaps detected. Skipping enrichment loop.")
                state.pipeline_step = "drafting"

        # 6. Enrichment Search
        if state.pipeline_step == "enrichment_searching":
            tracker.io_total += 1
            yield json.dumps({
                "status": "enrichment_searching", 
                "phase_current": 5, 
                "phase_total": 8, 
                "message": f"Running {len(state.enrichment_queries)} targeted enrichment searches...", 
                **tracker.as_dict()
            })
            state.search_queries = state.enrichment_queries
            state = await run_search(state)
            tracker.io_completed += 1
            state.pipeline_step = "enrichment_extracting"

        # 7. Enrichment Extract & Sieve
        if state.pipeline_step == "enrichment_extracting":
            tracker.io_total += len(state.urls)
            async for update in pipeline_sieve(6, is_enrichment=True): yield update
            
            # Store post-enrichment checkpoint for replay
            try:
                from llm import llm
                async with llm.counter_lock:
                    llm.inference_counter += 1
                    current_index = llm.inference_counter
                filepath = os.path.join(llm.log_dir, f"{current_index:04d}_EnrichmentCompleteData_output.json")
                with open(filepath, "w") as f:
                    json.dump({"status": "enrichment_loop_completed"}, f, indent=2)
                logger.debug(f"Enrichment checkpoint logged for replay: {filepath}")
            except Exception as e:
                logger.error(f"Failed to log EnrichmentCompleteData: {e}")

            state.pipeline_step = "drafting"

        # 8. Final Handoff (Parallel Drafting)
        if state.pipeline_step == "drafting":
            async for update in flow(run_drafter(state), 7):
                if "units_discovered" in (u := json.loads(update)):
                    tracker.llm_total += u["units_discovered"] * tracker.get_llm_multiplier()
                    continue
                yield update
            state.pipeline_step = "completed"

        # 9. Delivery
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
