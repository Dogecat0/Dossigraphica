import os
import asyncio
import time
import traceback
from datetime import datetime
import litellm
from pydantic import BaseModel, Field, create_model
from typing import Any, Type, TypeVar, List, get_origin, get_args, cast
import logging
import json
import jsonref
import re
from json_repair import repair_json
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
)
from pydantic import ValidationError
from litellm.exceptions import (
    RateLimitError,
    ServiceUnavailableError,
    APIConnectionError,
    InternalServerError,
    Timeout,
    MidStreamFallbackError,
)
from schemas import SummarySchema
import checkpoint
from provider import (
    ACTIVE_MODEL,
    ACTIVE_BASE_URL,
    ACTIVE_N_PARALLEL,
    ACTIVE_CTX_LIMIT,
    ACTIVE_CHUNK_SIZE,
    ACTIVE_OUTPUT_RESERVATION,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    LLM_OUTPUT_MODE,
    LLM_REQUEST_TIMEOUT,
    OUTPUT_RESERVATION,
    SAFETY_BUFFER,
    before_sleep_log_model,
    wait_if_not_timeout,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# DEBUG profile — per-LLM-call stack-trace logging
# Active when DEBUG_PROFILE=1 env var is set.
# Writes line-delimited JSON to logs/debug/llm_trace_TIMESTAMP.log
# ---------------------------------------------------------------------------

_DEBUG_TRACE_FILE = None
_DEBUG_TRACE_PATH = None

def _init_debug_trace():
    global _DEBUG_TRACE_FILE, _DEBUG_TRACE_PATH
    if not os.getenv("DEBUG_PROFILE", "").lower() in ("1", "true", "yes"):
        return None
    log_dir = os.path.join(os.path.dirname(__file__), "logs", "debug")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"llm_trace_{ts}.log")
    _DEBUG_TRACE_PATH = path
    _DEBUG_TRACE_FILE = open(path, "w", buffering=1)
    _debug_write("init", {"msg": "debug trace opened"})
    print(f"[DEBUG_PROFILE] LLM trace → {path}")
    return path

def _debug_write(kind: str, data: dict):
    f = _DEBUG_TRACE_FILE
    if f is None:
        return
    try:
        now = datetime.now().isoformat(timespec="milliseconds")
        line = json.dumps({"t": now, "kind": kind, **data}, default=str)
        f.write(line + "\n")
    except Exception:
        pass

def _close_debug_trace():
    global _DEBUG_TRACE_FILE, _DEBUG_TRACE_PATH
    if _DEBUG_TRACE_FILE:
        try:
            _DEBUG_TRACE_FILE.close()
        except Exception:
            pass
        _DEBUG_TRACE_FILE = None
    _DEBUG_TRACE_PATH = None

# Initialize on import
_init_debug_trace()
import atexit
atexit.register(_close_debug_trace)


class LLMClient:
    """
    Client wrapper for interacting with the LLM.
    Uses strict response_format and forces schema adherence via prompts.
    Centralized semaphore enforces the provider's parallel limit across all tasks.
    """

    def __init__(self, base_url: str = ACTIVE_BASE_URL, model: str = ACTIVE_MODEL):
        self.base_url = base_url
        self.model = model
        self.semaphore = asyncio.Semaphore(ACTIVE_N_PARALLEL)
        self.progress_queue: asyncio.Queue | None = None

        # Shared checkpoint counter + log directory (idempotent init)
        self.log_dir = checkpoint.init()

        # Suppress LiteLLM internal logging unless there is an error
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        litellm.set_verbose = False  # type: ignore[reportPrivateImportUsage]

        if not os.getenv("OPENAI_API_KEY") and not ACTIVE_BASE_URL:
            pass
        elif not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-no-key-required"

        # Force register model capabilities if using DeepSeek
        if LLM_PROVIDER == "deepseek":
            litellm.register_model({
                self.model: {
                    "supports_function_calling": True,
                    "supports_parallel_function_calling": False,
                }
            })

        logger.debug(
            "Initialized LLMClient provider=%s model=%s parallel_limit=%s ctx_limit=%s",
            LLM_PROVIDER, model, ACTIVE_N_PARALLEL, ACTIVE_CTX_LIMIT,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_safe_input_limit(self) -> int:
        """Absolute maximum input tokens allowed after reservation and safety buffer."""
        return ACTIVE_CTX_LIMIT - OUTPUT_RESERVATION - SAFETY_BUFFER

    def estimate_tokens(self, messages: List[dict]) -> int:
        """Accurate message list token counting using litellm."""
        return litellm.token_counter(model=self.model, messages=messages)

    def calculate_safe_chunk_size(
        self, system_prompt: str, user_prompt_template: str, response_model: Type[BaseModel],
    ) -> int:
        """How many tokens are left for a chunk given a prompt template and schema."""
        if ACTIVE_CHUNK_SIZE > 0:
            return ACTIVE_CHUNK_SIZE
        messages = self._construct_messages(
            user_prompt_template.format(chunk=""), system_prompt, response_model,
        )
        overhead = self.estimate_tokens(messages)
        safe_size = self.get_safe_input_limit() - overhead
        return max(512, safe_size)

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    async def save_checkpoint(self, name: str, data: dict) -> str:
        """Persist a pipeline checkpoint for state replay."""
        return await checkpoint.save_checkpoint(name, data)

    # ------------------------------------------------------------------
    # Structured generation
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str = "You are a professional research agent.",
        facts: str | None = None,
    ) -> T:
        current_index = await checkpoint.next_index()

        def _get_target_tokens(model):
            return self.calculate_safe_chunk_size(
                system_prompt, prompt.replace("__FACTS__", "{chunk}"), model,
            )

        if LLM_OUTPUT_MODE == "one-shot":
            if facts:
                target_tokens = _get_target_tokens(response_model)
                model_desc = response_model.model_json_schema().get("description", "")
                focus_context = f"{system_prompt} (Schema: {response_model.__name__} - {model_desc})"
                summary = await self.summarize_to_fit(facts, target_tokens, system_prompt, focus=focus_context)
                final_prompt = prompt.replace("__FACTS__", summary)
            else:
                final_prompt = prompt

            messages = self._construct_messages(final_prompt, system_prompt, response_model)
            input_tokens = self.estimate_tokens(messages)
            output_tokens = 0
            reasoning_tokens = 0
            _call_id = f"{current_index:04d}"
            try:
                res, output_tokens, reasoning_tokens = await self._generate_single_field(messages, response_model, current_index, "")
            finally:
                if self.progress_queue:
                    self.progress_queue.put_nowait({
                        "event": "llm_complete",
                        "call_id": _call_id,
                        "tokens": {"input": input_tokens, "output": output_tokens, "reasoning": reasoning_tokens, "cached_input": getattr(self, "_last_cached_input_tokens", 0), "cache_write": getattr(self, "_last_cache_write_tokens", 0)},
                    })
            return cast(T, res)

        # Multi-shot generation
        current_output = {}
        for i, (field_name, field_info) in enumerate(response_model.model_fields.items(), start=1):
            annotation = field_info.annotation
            FieldModel = create_model(
                field_name,
                **{field_name: (annotation, Field(..., description=field_info.description))},  # type: ignore[reportArgumentType, reportCallIssue]
            )

            field_facts = ""
            if facts:
                origin = get_origin(annotation)
                args = get_args(annotation)
                if origin is list and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    logger.debug("Decomposing list field '%s' into entity-level tasks.", field_name)

                    DiscoveryModel = create_model(
                        "Discovery",
                        reasoning=(str, Field(..., description="Logic for identifying unique entities.")),
                        entities=(List[str], Field(..., description=f"List of unique entities for {field_name}.")),
                    )
                    discovery_template = (
                        f"Identify all unique entities or specific items for the field '{field_name}' "
                        f"from the provided facts. Focus on: {field_info.description}\n\nFACTS:\n__FACTS__"
                    )
                    discovery_target = self.calculate_safe_chunk_size(
                        system_prompt,
                        discovery_template.replace("__FACTS__", "{chunk}"),
                        DiscoveryModel,
                    )
                    discovery_facts = await self.summarize_to_fit(
                        facts, discovery_target, system_prompt, focus=f"Entities for {field_name}",
                    )
                    discovery_res = await self.generate_structured(
                        prompt=discovery_template.replace("__FACTS__", discovery_facts),
                        response_model=DiscoveryModel,
                        system_prompt=system_prompt,
                    )

                    async def _extract_entity(entity_id: str) -> BaseModel:
                        entity_summary = await self.summarize_to_fit(
                            facts, _get_target_tokens(args[0]), system_prompt, focus=entity_id,
                        )
                        return await self.generate_structured(
                            prompt=f"Extract full details for the specific entity '{entity_id}' using these facts:\n{entity_summary}",
                            response_model=args[0],
                            system_prompt=system_prompt,
                        )

                    entities = await asyncio.gather(
                        *(_extract_entity(eid) for eid in cast(Any, discovery_res).entities)
                    )

                    current_output[field_name] = list(entities)
                    continue

                target_tokens = _get_target_tokens(FieldModel)
                field_facts = await self.summarize_to_fit(
                    facts, target_tokens, system_prompt, focus=field_info.description,
                )

            field_prompt = prompt.replace("__FACTS__", field_facts) if facts else prompt
            multi_shot_prompt = (
                f"{field_prompt}\n\n"
                f"--- MULTI-SHOT GENERATION PROGRESS ---\n"
                f"We are generating the final JSON object field by field.\n"
                f"Current output so far:\n```json\n{json.dumps(current_output, indent=2)}\n```\n\n"
                f"Your task is to generate the next field: `{field_name}`."
            )

            messages = self._construct_messages(
                multi_shot_prompt, system_prompt, response_model, function_name=field_name,
            )
            input_tokens = self.estimate_tokens(messages)
            output_tokens = 0
            reasoning_tokens = 0
            _call_id = f"{current_index:04d}_{i:02d}"
            try:
                partial_result, output_tokens, reasoning_tokens = await self._generate_single_field(
                    messages, FieldModel, current_index, f"_{i:02d}",
                    log_model_name=response_model.__name__,
                )
            finally:
                if self.progress_queue:
                    self.progress_queue.put_nowait({
                        "event": "llm_complete",
                        "call_id": _call_id,
                        "tokens": {"input": input_tokens, "output": output_tokens, "reasoning": reasoning_tokens, "cached_input": getattr(self, "_last_cached_input_tokens", 0), "cache_write": getattr(self, "_last_cache_write_tokens", 0)},
                    })

            field_value = getattr(partial_result, field_name)
            current_output[field_name] = field_value

        return response_model(**current_output)

    # ------------------------------------------------------------------
    # Map-reduce summarization
    # ------------------------------------------------------------------

    async def summarize_to_fit(
        self,
        content: str,
        target_tokens: int,
        system_prompt: str = "You are a data compression specialist.",
        focus: str | None = None,
        filter_relevance: bool = False,
    ) -> str:
        """Recursively summarizes content using Map-Reduce parallelization until it fits.

        When *filter_relevance* is True, each chunk's SummarySchema is checked for
        ``is_relevant`` — irrelevant chunks are dropped entirely. This is used by
        ``get_fact_subset`` to discard off-topic material. Defaults to False for
        backward compatibility with all other callers.
        """
        current_tokens = self.estimate_tokens([{"role": "user", "content": content}])

        if current_tokens <= target_tokens:
            return content

        if focus:
            summary_template = (
                f"Following content is too long. Extract and condense ONLY the facts "
                f"relevant to: {focus}. "
                "MANDATE: You MUST preserve all exact numerical values, technical metrics, "
                "units of measure, specific dates, and proper names. "
                "Omit irrelevant material entirely. If some relevant facts are found "
                "mixed with irrelevant content, extract only the relevant parts. "
                "Produce a condensed version significantly shorter than the original. "
                "Eliminate redundancy and narrative fluff. Do not rephrase verbatim.\n{chunk}"
            )
        else:
            summary_template = (
                "Following content is too long. Extract and condense ONLY the relevant facts. "
                "MANDATE: You MUST preserve all exact numerical values, technical metrics, "
                "units of measure, specific dates, and proper names. "
                "Omit irrelevant material entirely. If some relevant facts are found "
                "mixed with irrelevant content, extract only the relevant parts. "
                "Produce a condensed version significantly shorter than the original. "
                "Eliminate redundancy and narrative fluff. Do not rephrase verbatim.\n{chunk}"
            )

        safe_chunk_tokens = self.calculate_safe_chunk_size(system_prompt, summary_template, SummarySchema)

        logger.debug(
            "Map-Reduce Summary: %s tokens -> target %s. Chunking at %s.",
            current_tokens, target_tokens, safe_chunk_tokens,
        )

        # Split content into token-aware chunks
        try:
            tokens = litellm.encode(model=self.model, text=content)
            chunks = []
            for i in range(0, len(tokens), safe_chunk_tokens):
                chunk_tokens = tokens[i : i + safe_chunk_tokens]
                chunks.append(litellm.decode(model=self.model, tokens=chunk_tokens))
        except Exception:
            char_size = safe_chunk_tokens * 4
            chunks = [content[i : i + char_size] for i in range(0, len(content), char_size)]

        async def summarize_chunk(chunk_text: str) -> str:
            prompt = summary_template.format(chunk=chunk_text)
            res = await self.generate_structured(prompt, SummarySchema, system_prompt)
            if filter_relevance and not res.is_relevant:
                return ""
            return res.summary or ""

        summaries = await asyncio.gather(*(summarize_chunk(c) for c in chunks))
        if filter_relevance:
            combined_summary = "\n\n".join(s for s in summaries if s)
        else:
            combined_summary = "\n\n".join(summaries)

        return await self.summarize_to_fit(combined_summary, target_tokens, system_prompt, focus=focus)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _construct_messages(
        self, prompt: str, system_prompt: str, response_model: Type[BaseModel],
        function_name: str | None = None,
    ) -> List[dict]:
        raw_schema = response_model.model_json_schema()
        deref_schema = jsonref.replace_refs(raw_schema, proxies=False)
        deref_schema.pop("$defs", None)

        schema_json = json.dumps(deref_schema, indent=2)
        now = datetime.now().isoformat()

        call_instruction = (
            f"5. You MUST call the function `{function_name}` to submit your result.\n"
            if function_name else ""
        )

        strict_system_prompt = (
            f"{system_prompt}\n\n"
            f"CURRENT_TIME: {now}\n\n"
            "STRICT INSTRUCTIONS:\n"
            "1. You MUST respond with ONLY a valid JSON object.\n"
            "2. You MUST NOT add any extra fields or rename keys.\n"
            "3. All keys and string values MUST be enclosed in double quotes (\"). "
            "This is MANDATORY, especially if the text contains commas or periods.\n"
            "4. If a property is nullable and you have no data, output the keyword `null` "
            "(WITHOUT double quotes). If a property is required and NOT nullable, "
            "you MUST provide a valid value.\n"
            f"{call_instruction}"
            "Do NOT include markdown code blocks or preamble text.\n\n"
            f"REQUIRED SCHEMA:\n{schema_json}"
        )
        return [
            {"role": "system", "content": strict_system_prompt},
            {"role": "user", "content": prompt},
        ]

    def _parse_unquoted_custom_syntax(self, content: str, deref_schema: dict) -> str:
        """
        Parses Hermes-style unquoted tool calls (e.g. call:Name{key:val,with,commas})
        by dynamically anchoring on the known schema keys to avoid splitting on internal commas.
        """
        import json as _json

        def get_keys(schema):
            keys = set()
            if "properties" in schema:
                keys.update(schema["properties"].keys())
                for v in schema["properties"].values():
                    keys.update(get_keys(v))
            if "items" in schema:
                keys.update(get_keys(schema["items"]))
            return keys

        schema_keys = list(get_keys(deref_schema))
        if not schema_keys:
            return content

        keys_pattern = "|".join(schema_keys)
        regex = rf"({keys_pattern}):(.*?)(?=,(?:{keys_pattern}):|$)"

        match = re.search(r"call:\w+\{(.*)\}", content, re.DOTALL)
        if not match:
            return content

        inner = match.group(1)

        # Array payload handling (e.g. {extracted_facts:[{...},{...}]})
        list_match = re.search(r"\[(.*)\]", inner, re.DOTALL)
        if list_match:
            top_key_match = re.search(r"(\w+):\[", inner)
            top_key = top_key_match.group(1) if top_key_match else list(schema_keys)[0]

            list_content = list_match.group(1)
            objects = re.findall(r"\{(.*?)\}", list_content, re.DOTALL)

            parsed_objects = []
            for obj in objects:
                fields = re.finditer(regex, obj, re.DOTALL)
                parsed_obj = {
                    f.group(1): f.group(2).strip().strip('"').strip("'")
                    for f in fields
                }
                if parsed_obj:
                    parsed_objects.append(parsed_obj)
            return _json.dumps({top_key: parsed_objects})
        else:
            fields = re.finditer(regex, inner, re.DOTALL)
            parsed_obj = {
                f.group(1): f.group(2).strip().strip('"').strip("'")
                for f in fields
            }
            return _json.dumps(parsed_obj) if parsed_obj else content

    async def _log_inference(
        self, current_index: int, messages: List[dict], model_name: str,
        raw_response: str, step_suffix: str = "",
    ) -> float:
        """Logs the raw inputs and outputs to separate, readable files. Returns write duration in seconds."""
        base_name = f"{current_index:04d}_{model_name}{step_suffix}"

        input_path = os.path.join(self.log_dir, f"{base_name}_input.md")
        system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "N/A")
        user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "N/A")

        input_md = (
            f"# Inference {current_index:04d} - {model_name}{step_suffix}\n\n"
            f"**Model:** `{self.model}`\n\n"
            f"## System Prompt\n\n{system_prompt}\n\n"
            f"## User Prompt\n\n{user_prompt}\n"
        )

        output_path = os.path.join(self.log_dir, f"{base_name}_output.json")
        reasoning_path = os.path.join(self.log_dir, f"{base_name}_reasoning.md")

        parsed_json = None
        try:
            repaired = repair_json(raw_response)
            parsed_json = json.loads(repaired)
            formatted_output = json.dumps(parsed_json, indent=2)
        except Exception:
            formatted_output = raw_response

        _io_start = time.monotonic()
        try:
            with open(input_path, "w") as f:
                f.write(input_md)
            with open(output_path, "w") as f:
                f.write(formatted_output)
            if parsed_json and isinstance(parsed_json, dict) and "reasoning" in parsed_json:
                with open(reasoning_path, "w") as f:
                    f.write(f"# Reasoning - {base_name}\n\n{parsed_json['reasoning']}\n")
            logger.debug("Inference logged: %s", base_name)
        except Exception as e:
            logger.error("Failed to log inference files: %s", e)
        _io_dur = time.monotonic() - _io_start
        return _io_dur

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_if_not_timeout,
        retry=(
            retry_if_exception_type(RateLimitError)
            | retry_if_exception_type(ServiceUnavailableError)
            | retry_if_exception_type(MidStreamFallbackError)
            | retry_if_exception_type(APIConnectionError)
            | retry_if_exception_type(InternalServerError)
            | retry_if_exception_type(Timeout)
            | retry_if_exception_type(ValidationError)
            | retry_if_exception_type(ValueError)
        ),
        before_sleep=before_sleep_log_model(logger, logging.WARNING),
        reraise=True,
    )
    async def _generate_single_field(
        self,
        messages: List[dict],
        response_model: Type[BaseModel],
        current_index: int,
        step_suffix: str,
        log_model_name: str | None = None,
    ) -> tuple[BaseModel, int, int]:
        _call_start_time = time.monotonic()
        _sem_acquired_time = None

        # DEBUG trace: log before LLM call with stack trace
        _debug_write("llm_start", {
            "schema": log_model_name or response_model.__name__,
            "stack": "\n".join(traceback.format_stack()[:-1]),
        })

        async with self.semaphore:
            _sem_acquired_time = time.monotonic()
            _sem_wait = _sem_acquired_time - _call_start_time
            if _sem_wait > 1.0:
                logger.warning(
                    "Semaphore wait %.1fs for %s (slots: %d/%d)",
                    _sem_wait, response_model.__name__,
                    ACTIVE_N_PARALLEL - self.semaphore._value, ACTIVE_N_PARALLEL,
                )
            _debug_write("sem_acquired", {
                "schema": log_model_name or response_model.__name__,
                "wait_s": round(_sem_wait, 3),
            })
            try:
                raw_schema = response_model.model_json_schema()
                deref_schema = jsonref.replace_refs(raw_schema, proxies=False)  # type: ignore[reportIndexIssue]
                deref_schema.pop("$defs", None)  # type: ignore[reportAttributeAccessIssue, reportCallIssue]
                deref_schema["required"] = list(response_model.model_fields.keys())  # type: ignore[reportIndexIssue]

                logger.debug("LLM Call: %s | model=%s", response_model.__name__, self.model)

                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "api_base": self.base_url,
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": ACTIVE_OUTPUT_RESERVATION,
                    "timeout": LLM_REQUEST_TIMEOUT,
                    "add_function_to_prompt": False,
                    "num_retries": 0,
                    "stream": True,
                }

                if LLM_PROVIDER == "gemini":
                    kwargs["response_format"] = {
                        "type": "json_object",
                        "response_schema": deref_schema,
                    }
                elif LLM_PROVIDER == "deepseek":
                    # DeepSeek strict mode: tool calls with strict schema constraints.
                    # Every nested object must have additionalProperties: false.
                    def _ensure_strict(obj: dict) -> dict:
                        if isinstance(obj, dict):
                            if obj.get("type") == "object":
                                obj["additionalProperties"] = False
                            for v in obj.values():
                                _ensure_strict(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                _ensure_strict(item)
                        return obj
                    _ensure_strict(deref_schema)  # type: ignore[reportArgumentType]
                    kwargs["tools"] = [{
                        "type": "function",
                        "function": {
                            "name": response_model.__name__,
                            "description": "Submit structured research data.",
                            "parameters": deref_schema,
                            "strict": True,
                        },
                    }]
                    kwargs["tool_choice"] = {
                        "type": "function",
                        "function": {"name": response_model.__name__},
                    }
                    # Thinking mode is incompatible with tool_choice.
                    # All structured generation uses tool calls, so thinking must be disabled.
                    kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                else:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__,
                            "strict": True,
                            "schema": deref_schema,
                        },
                    }

                response = await litellm.acompletion(**kwargs)

                content = ""
                reasoning_content_text = ""
                _cached_input_tokens = 0
                _cache_write_tokens = 0
                if kwargs.get("stream"):
                    # Per-chunk timeout: generous for the first chunk (server needs to
                    # start generating), then tight inter-chunk timeout.  This detects
                    # mid-stream stalls within seconds instead of waiting for a full fixed
                    # deadline, while still allowing slow-start servers enough time.
                    _print_stream = os.getenv("LLM_DEBUG_STREAM", "false").lower() == "true"
                    _stream_iter = response.__aiter__()  # type: ignore[reportAttributeAccessIssue]
                    _first_chunk = True
                    _stream_chunk_count = 0
                    while True:
                        _chunk_timeout = (
                            LLM_REQUEST_TIMEOUT + 30
                            if _first_chunk
                            else max(15, LLM_REQUEST_TIMEOUT // 2)
                        )
                        try:
                            chunk = await asyncio.wait_for(
                                _stream_iter.__anext__(),
                                timeout=_chunk_timeout,
                            )
                            _first_chunk = False
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            try:
                                await response.aclose()  # type: ignore[reportAttributeAccessIssue]
                            except Exception:
                                pass
                            _llm_provider = self.model.split("/")[0] if "/" in self.model else self.model
                            raise Timeout(
                                f"Stream response timed out after {_chunk_timeout}s (inter-chunk)",
                                self.model,
                                _llm_provider,
                            )

                        # Capture usage from the final chunk (has usage but empty choices)
                        _chunk_usage = chunk.usage  # type: ignore[reportAttributeAccessIssue]
                        if _chunk_usage is not None:
                            _prompt_d = getattr(_chunk_usage, "prompt_tokens_details", None)
                            if _prompt_d is not None:
                                _ct = getattr(_prompt_d, "cached_tokens", None)
                                if _ct is not None:
                                    _cached_input_tokens = _ct
                            _cr = getattr(_chunk_usage, "cache_read_input_tokens", None)
                            if _cr is not None:
                                _cached_input_tokens = _cr
                            _cw = getattr(_chunk_usage, "cache_creation_input_tokens", None)
                            if _cw is not None:
                                _cache_write_tokens = _cw

                        if chunk.choices and len(chunk.choices) > 0:  # type: ignore[reportOptionalSubscript]
                            delta = chunk.choices[0].delta
                            delta_text = ""

                            if getattr(delta, "reasoning_content", None):
                                reasoning_content_text += delta.reasoning_content or ""
                                delta_text = delta.reasoning_content
                            elif delta.content:
                                content += delta.content
                                delta_text = delta.content
                            elif getattr(delta, "tool_calls", None):
                                tc = delta.tool_calls[0]  # type: ignore[reportOptionalSubscript]
                                if getattr(tc, "function", None) and tc.function.arguments:
                                    content += tc.function.arguments
                                    delta_text = tc.function.arguments

                            if delta_text:
                                if len(content) > ACTIVE_OUTPUT_RESERVATION * 6:
                                    raise ValueError(
                                        "Runaway generation detected: output exceeded maximum expected character limit."
                                    )
                                tail = content[-250:]
                                if len(tail) >= 100:
                                    match = re.search(r"([^\{\}\[\]\"]{10,60}?)\1{3,}$", tail)
                                    if match and re.search(r"[a-zA-Z]", match.group(1)):
                                        raise ValueError(
                                            "Dynamic text repetition loop detected in output stream."
                                        )
                                if _print_stream:
                                    print(delta_text, end="", flush=True)

                            # Every 15 chunks push a live token estimate so the progress
                            # bar ticks during long generations (hang detection).
                            _stream_chunk_count += 1
                            if self.progress_queue and _stream_chunk_count % 15 == 0:
                                _est_out = len(content) // 4
                                _est_reas = len(reasoning_content_text) // 4
                                _stream_call_id = f"{current_index:04d}{step_suffix}"
                                self.progress_queue.put_nowait({
                                    "type": "stream_estimate",
                                    "call_id": _stream_call_id,
                                    "estimated_output_tokens": _est_out,
                                    "estimated_reasoning_tokens": _est_reas,
                                })

                    if _print_stream:
                        print()
                else:
                    message = response.choices[0].message  # type: ignore[reportAttributeAccessIssue]
                    content = message.content or ""
                    reasoning_content_text = getattr(message, "reasoning_content", None) or ""
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls and len(tool_calls) > 0 and tool_calls[0].function:
                        content = tool_calls[0].function.arguments

                # Log combined content, parse normal content only
                _log_full_response = reasoning_content_text + content
                if not _log_full_response:
                    raise ValueError("LLM returned empty content and no tool calls.")

            except (
                RateLimitError, ServiceUnavailableError, MidStreamFallbackError,
                APIConnectionError, InternalServerError, Timeout, ValueError, ValidationError,
            ) as e:
                logger.error(
                    "Structured Generation attempt failed for model '%s': %s: %s",
                    self.model, type(e).__name__, e,
                )
                raise
            except Exception as e:
                logger.critical(
                    "Unrecoverable Structured Generation Error for model '%s': %s: %s",
                    self.model, type(e).__name__, e,
                )
                raise

        self._last_cached_input_tokens = _cached_input_tokens
        self._last_cache_write_tokens = _cache_write_tokens

        # --- Semaphore released: log and parse outside the concurrency gate ---
        name_for_logging = log_model_name or response_model.__name__
        _io_start_time = time.monotonic()
        _io_write_dur = await self._log_inference(current_index, messages, name_for_logging, _log_full_response, step_suffix)

        try:
            if content.startswith("call:"):
                content = self._parse_unquoted_custom_syntax(content, deref_schema)  # type: ignore[reportArgumentType]
                parsed_model = response_model.model_validate_json(content)
            else:
                content = repair_json(content)
                parsed_model = response_model.model_validate_json(content)
        except Exception as e:
            logger.error("Pydantic Validation Failure: %s. Content: %s", e, content)
            raise

        # Compute output and reasoning tokens from the raw response
        output_tokens = litellm.token_counter(model=self.model, text=content) if content else 0
        reasoning_tokens = litellm.token_counter(model=self.model, text=reasoning_content_text) if reasoning_content_text else 0

        _now = time.monotonic()
        _sem_wait_logged = _sem_acquired_time - _call_start_time if _sem_acquired_time else 0
        _llm_dur = _now - _sem_acquired_time if _sem_acquired_time else _now - _call_start_time
        _total_dur = _now - _call_start_time

        # Save exact token metadata for replay recovery (used by pipeline.py)
        _input_tok = litellm.token_counter(model=self.model, messages=messages)
        try:
            _meta_base = f"{current_index:04d}_{name_for_logging}{step_suffix}"
            _meta_path = os.path.join(self.log_dir, f"{_meta_base}_meta.json")
            with open(_meta_path, "w") as _mf:
                json.dump({
                    "input_tokens": _input_tok,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "cached_input_tokens": _cached_input_tokens,
                    "cache_write_tokens": _cache_write_tokens,
                }, _mf)
        except Exception:
            pass

        # DEBUG trace: log completion with timing breakdown
        _debug_write("llm_end", {
            "schema": response_model.__name__,
            "total_s": round(_total_dur, 3),
            "sem_wait_s": round(_sem_wait_logged, 3),
            "llm_call_s": round(_llm_dur, 3),
            "io_write_s": round(_io_write_dur, 3),
            "input_tokens": _input_tok if _DEBUG_TRACE_FILE else 0,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
        })

        return parsed_model, output_tokens, reasoning_tokens
