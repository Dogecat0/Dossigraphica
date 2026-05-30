"""
Shared checkpoint persistence — decoupled from LLMClient.

Both the LLM inference logger and pipeline stages (search, extraction)
write ordered checkpoints to the same directory so that log replay can
reconstruct ResearchState across runs.
"""

import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

_log_dir: str | None = None
_counter: int = 0
_counter_lock: asyncio.Lock | None = None


def init(log_dir: str | None = None) -> str:
    """Initialise the shared counter and log directory. Idempotent.  Returns the active log_dir."""
    global _counter, _counter_lock, _log_dir

    if _counter_lock is None:
        _counter_lock = asyncio.Lock()

    if log_dir is not None and _log_dir is None:
        _log_dir = log_dir
    elif _log_dir is None:
        _log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")

    os.makedirs(_log_dir, exist_ok=True)

    if _counter == 0:
        max_idx = 0
        if os.path.exists(_log_dir):
            import re
            for f in os.listdir(_log_dir):
                match = re.match(r"^(\d+)_", f)
                if match:
                    idx = int(match.group(1))
                    if idx > max_idx:
                        max_idx = idx
        _counter = max_idx

    return _log_dir


async def next_index() -> int:
    """Atomically bump and return the next checkpoint index."""
    global _counter
    assert _counter_lock is not None, "checkpoint.init() must be called before next_index()"
    async with _counter_lock:
        _counter += 1
        return _counter


async def save_checkpoint(name: str, data: dict) -> str:
    """Persist a pipeline checkpoint and return its file path."""
    assert _log_dir is not None, "checkpoint.init() must be called before save_checkpoint()"
    idx = await next_index()
    filepath = os.path.join(_log_dir, f"{idx:04d}_{name}_output.json")
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug("Checkpoint saved: %s → %s", name, filepath)
    except Exception as e:
        logger.error("Failed to save checkpoint %s: %s", name, e)
    return filepath
