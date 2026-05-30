"""
LLM provider configuration and retry helpers.

All environment-variable-driven configuration lives here so that
different parts of the system can import constants without pulling
in the full LLMClient class.
"""

import os
import json
import logging
from dotenv import load_dotenv
from tenacity import wait_exponential
import litellm
from litellm.exceptions import Timeout

# Load .env — PWD overrides all. Pipeline root overrides project root.
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)
load_dotenv('.env', override=True)  # PWD wins

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


class _NewlineHandler(logging.StreamHandler):
    """Ensures log messages never collide with the progress bar.

    Behavior by context:

    * **TTY + tqdm active** — delegates to ``tqdm.write()``, which
      clears the current bar line, writes the log message above it,
      and redraws the bar on the last line. This keeps the progress
      bar anchored at the bottom of the terminal at all times.

    * **TTY + no tqdm** — prepends ``\\n`` so the message starts on
      a fresh line (safety net against any other ``\\r``-based
      output).

    * **Non-TTY (pipe, file, Docker)** — writes the message as-is
      with no prefix.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            if not stream.isatty():
                stream.write(msg + self.terminator)
            else:
                # If tqdm is active, use tqdm.write() which clears the bar,
                # writes the message above it, and redraws the bar at the
                # bottom of the terminal. This keeps the progress bar anchored
                # below all log output.
                try:
                    import tqdm as _tqdm
                    if getattr(_tqdm.tqdm, '_instances', None):
                        _tqdm.tqdm.write(msg, file=stream, end=self.terminator)
                        self.flush()
                        return
                except (ImportError, Exception):
                    pass
                stream.write("\n" + msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


# Replace the default stream handler (added by basicConfig) with our
# newline-safe variant so all logger output respects the progress bar.
# We preserve the formatter from the original handler to keep the log
# format unchanged (``LEVEL:name:message``).
_root = logging.getLogger()
_formatter = None
for _h in list(_root.handlers):
    if isinstance(_h, logging.StreamHandler):
        _formatter = _h.formatter
    _root.removeHandler(_h)
_new_h = _NewlineHandler()
if _formatter:
    _new_h.setFormatter(_formatter)
_root.addHandler(_new_h)


# ---------------------------------------------------------------------------
# Retry helpers (shared by LLMClient)
# ---------------------------------------------------------------------------
def before_sleep_log_model(logger_obj, log_level):
    def log_it(retry_state):
        if retry_state.outcome.failed:
            ex = retry_state.outcome.exception()
            self_instance = retry_state.args[0]
            verb, value = "raised", f"{type(ex).__name__}: {ex}"
            logger_obj.log(
                log_level,
                f"Retrying structured generation (attempt {retry_state.attempt_number}) "
                f"for model '{self_instance.model}' "
                f"in {retry_state.next_action.sleep} seconds as it {verb} {value}",
            )
    return log_it


_backoff = wait_exponential(multiplier=2, min=10, max=60)


def wait_if_not_timeout(retry_state):
    """Timeout → immediate retry; all other transient errors → exponential backoff."""
    if isinstance(retry_state.outcome.exception(), Timeout):
        return 0
    return _backoff(retry_state)


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local").lower()

# -- Local Llama.cpp --------------------------------------------------------
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8081/v1/")
LLAMA_N_PARALLEL = int(os.getenv("LLAMA_N_PARALLEL", "1"))
LLAMA_CTX_PER_REQUEST = int(os.getenv("LLAMA_CTX_PER_REQUEST", "8192"))
LLAMA_MODEL = os.getenv("LLAMA_MODEL_REPO", "unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_M")

# -- Gemini -----------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-3.1-flash-lite-preview")
GEMINI_N_PARALLEL = int(os.getenv("GEMINI_N_PARALLEL", "10"))
GEMINI_CTX_PER_REQUEST = int(os.getenv("GEMINI_CTX_PER_REQUEST", "32768"))

# -- DeepSeek ----------------------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_N_PARALLEL = int(os.getenv("DEEPSEEK_N_PARALLEL", "10"))
DEEPSEEK_CTX_PER_REQUEST = int(os.getenv("DEEPSEEK_CTX_PER_REQUEST", "131072"))
DEEPSEEK_CHUNK_SIZE = int(os.getenv("DEEPSEEK_CHUNK_SIZE", "0"))
GEMINI_CHUNK_SIZE = int(os.getenv("GEMINI_CHUNK_SIZE", "0"))
LLAMA_CHUNK_SIZE = int(os.getenv("LLAMA_CHUNK_SIZE", "0"))

# -- Output / safety --------------------------------------------------------
# OUTPUT_RESERVATION is the baseline (local-provider) default.
# GEMINI_OUTPUT_RESERVATION and DEEPSEEK_OUTPUT_RESERVATION override it
# for their respective providers; each falls back to OUTPUT_RESERVATION.
OUTPUT_RESERVATION = int(os.getenv("OUTPUT_RESERVATION", "4096"))
GEMINI_OUTPUT_RESERVATION = int(os.getenv("GEMINI_OUTPUT_RESERVATION", str(OUTPUT_RESERVATION)))
DEEPSEEK_OUTPUT_RESERVATION = int(os.getenv("DEEPSEEK_OUTPUT_RESERVATION", "8192"))
SAFETY_BUFFER = 64

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_OUTPUT_MODE = os.getenv("LLM_OUTPUT_MODE", "multi-shot").lower()
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Active configuration (selected based on LLM_PROVIDER)
# ---------------------------------------------------------------------------
if LLM_PROVIDER == "gemini":
    ACTIVE_MODEL = GEMINI_MODEL
    ACTIVE_BASE_URL = None
    ACTIVE_N_PARALLEL = GEMINI_N_PARALLEL
    ACTIVE_CTX_LIMIT = GEMINI_CTX_PER_REQUEST
    ACTIVE_OUTPUT_RESERVATION = GEMINI_OUTPUT_RESERVATION
    ACTIVE_CHUNK_SIZE = GEMINI_CHUNK_SIZE
    if GEMINI_API_KEY:
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    logger.debug(
        "LLM Provider: GEMINI (model=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_OUTPUT_RESERVATION,
    )
elif LLM_PROVIDER == "deepseek":
    ACTIVE_MODEL = f"openai/{DEEPSEEK_MODEL}"
    ACTIVE_BASE_URL = "https://api.deepseek.com/beta"
    ACTIVE_N_PARALLEL = DEEPSEEK_N_PARALLEL
    ACTIVE_CTX_LIMIT = DEEPSEEK_CTX_PER_REQUEST
    ACTIVE_OUTPUT_RESERVATION = DEEPSEEK_OUTPUT_RESERVATION
    ACTIVE_CHUNK_SIZE = DEEPSEEK_CHUNK_SIZE
    if DEEPSEEK_API_KEY:
        os.environ["OPENAI_API_KEY"] = DEEPSEEK_API_KEY
    logger.debug(
        "LLM Provider: DEEPSEEK (model=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_OUTPUT_RESERVATION,
    )
else:
    ACTIVE_MODEL = f"openai/{LLAMA_MODEL}"
    ACTIVE_BASE_URL = LLAMA_CPP_URL
    ACTIVE_N_PARALLEL = LLAMA_N_PARALLEL
    ACTIVE_CTX_LIMIT = LLAMA_CTX_PER_REQUEST
    ACTIVE_OUTPUT_RESERVATION = OUTPUT_RESERVATION
    ACTIVE_CHUNK_SIZE = LLAMA_CHUNK_SIZE
    logger.debug(
        "LLM Provider: LOCAL (model=%s, url=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_BASE_URL, ACTIVE_OUTPUT_RESERVATION,
    )

# ---------------------------------------------------------------------------
# Custom model cost registration (takes precedence over litellm built-in)
# ---------------------------------------------------------------------------
_custom_costs_path = os.path.join(os.path.dirname(__file__), "custom_model_costs.json")
if os.path.exists(_custom_costs_path):
    try:
        with open(_custom_costs_path) as _cf:
            _custom_costs = json.load(_cf)
        for _mname, _mcost in _custom_costs.items():
            # Overwrite even if litellm already has it — custom file wins
            litellm.model_cost[_mname] = {
                "input_cost_per_token": _mcost["input_cost_per_token"],
                "output_cost_per_token": _mcost["output_cost_per_token"],
                "input_cache_hit_cost_per_token": _mcost.get("input_cache_hit_cost_per_token", _mcost["input_cost_per_token"]),
                "input_cache_write_cost_per_token": _mcost.get("input_cache_write_cost_per_token", _mcost["input_cost_per_token"]),
            }
            logger.info(
                "Registered custom cost rates for '%s': in=$%.2e out=$%.2e cache_hit=$%.2e cache_write=$%.2e",
                _mname,
                _mcost["input_cost_per_token"],
                _mcost["output_cost_per_token"],
                _mcost.get("input_cache_hit_cost_per_token", _mcost["input_cost_per_token"]),
                _mcost.get("input_cache_write_cost_per_token", _mcost["input_cost_per_token"]),
            )
    except Exception as _e:
        logger.warning("Failed to load custom model costs: %s", _e)

print(
    f"[CONFIG] provider={LLM_PROVIDER} "
    f"model={ACTIVE_MODEL} "
    f"context_limit={ACTIVE_CTX_LIMIT} "
    f"output_reservation={ACTIVE_OUTPUT_RESERVATION} "
    f"chunk_size={ACTIVE_CHUNK_SIZE or 'auto'} "
    f"n_parallel={ACTIVE_N_PARALLEL}"
)
