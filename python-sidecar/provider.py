"""
LLM provider configuration and retry helpers.

All environment-variable-driven configuration lives here so that
different parts of the system can import constants without pulling
in the full LLMClient class.
"""

import os
import logging
from tenacity import wait_exponential
from litellm.exceptions import Timeout

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


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

# -- Featherless ------------------------------------------------------------
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "moonshotai/Kimi-K2.6")
FEATHERLESS_N_PARALLEL = int(os.getenv("FEATHERLESS_N_PARALLEL", "1"))
FEATHERLESS_CTX_PER_REQUEST = int(os.getenv("FEATHERLESS_CTX_PER_REQUEST", "32768"))

# -- Output / safety --------------------------------------------------------
# OUTPUT_RESERVATION is the baseline (local-provider) default.
# GEMINI_OUTPUT_RESERVATION and FEATHERLESS_OUTPUT_RESERVATION override it
# for their respective providers; each falls back to OUTPUT_RESERVATION.
OUTPUT_RESERVATION = int(os.getenv("OUTPUT_RESERVATION", "4096"))
GEMINI_OUTPUT_RESERVATION = int(os.getenv("GEMINI_OUTPUT_RESERVATION", str(OUTPUT_RESERVATION)))
FEATHERLESS_OUTPUT_RESERVATION = int(os.getenv("FEATHERLESS_OUTPUT_RESERVATION", str(OUTPUT_RESERVATION)))
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
    if GEMINI_API_KEY:
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    logger.debug(
        "LLM Provider: GEMINI (model=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_OUTPUT_RESERVATION,
    )
elif LLM_PROVIDER == "featherless":
    ACTIVE_MODEL = f"openai/{FEATHERLESS_MODEL}"
    ACTIVE_BASE_URL = FEATHERLESS_BASE_URL
    ACTIVE_N_PARALLEL = FEATHERLESS_N_PARALLEL
    ACTIVE_CTX_LIMIT = FEATHERLESS_CTX_PER_REQUEST
    ACTIVE_OUTPUT_RESERVATION = FEATHERLESS_OUTPUT_RESERVATION
    if FEATHERLESS_API_KEY:
        os.environ["OPENAI_API_KEY"] = FEATHERLESS_API_KEY
    logger.debug(
        "LLM Provider: FEATHERLESS (model=%s, url=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_BASE_URL, ACTIVE_OUTPUT_RESERVATION,
    )
else:
    ACTIVE_MODEL = f"openai/{LLAMA_MODEL}"
    ACTIVE_BASE_URL = LLAMA_CPP_URL
    ACTIVE_N_PARALLEL = LLAMA_N_PARALLEL
    ACTIVE_CTX_LIMIT = LLAMA_CTX_PER_REQUEST
    ACTIVE_OUTPUT_RESERVATION = OUTPUT_RESERVATION
    logger.debug(
        "LLM Provider: LOCAL (model=%s, url=%s, output_reservation=%s)",
        ACTIVE_MODEL, ACTIVE_BASE_URL, ACTIVE_OUTPUT_RESERVATION,
    )
