import os
import asyncio
from datetime import datetime
import litellm
from pydantic import BaseModel, Field, create_model
from typing import Type, TypeVar, List
import logging
import json
import jsonref
import re
from json_repair import repair_json
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep_log,
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
from schemas import STRICT_CONFIG, SummarySchema
from provider import (
    ACTIVE_MODEL,
    ACTIVE_BASE_URL,
    ACTIVE_N_PARALLEL,
    ACTIVE_CTX_LIMIT,
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
        self.counter_lock = asyncio.Lock()
        self.inference_counter = 0
        self.log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
        self.progress_queue = None
        os.makedirs(self.log_dir, exist_ok=True)

        # Initialize inference counter from existing logs so replay won't overwrite
        max_idx = 0
        if os.path.exists(self.log_dir):
            for f in os.listdir(self.log_dir):
                match = re.match(r"^(\d+)_", f)
                if match:
                    idx = int(match.group(1))
                    if idx > max_idx:
                        max_idx = idx
        self.inference_counter = max_idx

        # Suppress LiteLLM internal logging unless there is an error
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        litellm.set_verbose = False

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
        async with self.counter_lock:
            self.inference_counter += 1
            current_index = self.inference_counter
        filepath = os.path.join(self.log_dir, f"{current_index:04d}_{name}_output.json")
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug("Checkpoint saved: %s → %s", name, filepath)
        except Exception as e:
            logger.error("Failed to save checkpoint %s: %s", name, e)
        return filepath

    # ------------------------------------------------------------------
    # Structured generation
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str = "You are a professional research agent.",
        facts: str = None,
    ) -> T:
        async with self.counter_lock:
            self.inference_counter += 1
            current_index = self.inference_counter

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
            try:
                res = await self._generate_single_field(messages, response_model, current_index, "")
            finally:
                if self.progress_queue:
                    self.progress_queue.put_nowait(True)
            return res

        # Multi-shot generation
        current_output = {}
        for i, (field_name, field_info) in enumerate(response_model.model_fields.items(), start=1):
            annotation = field_info.annotation
            FieldModel = create_model(
                field_name,
                **{field_name: (annotation, Field(..., description=field_info.description))},
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

                    entities = []
                    for entity_id in discovery_res.entities:
                        entity_summary = await self.summarize_to_fit(
                            facts, _get_target_tokens(args[0]), system_prompt, focus=entity_id,
                        )
                        entity_item = await self.generate_structured(
                            prompt=f"Extract full details for the specific entity '{entity_id}' using these facts:\n{entity_summary}",
                            response_model=args[0],
                            system_prompt=system_prompt,
                        )
                        entities.append(entity_item)

                    current_output[field_name] = entities
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
            try:
                partial_result = await self._generate_single_field(
                    messages, FieldModel, current_index, f"_{i:02d}",
                    log_model_name=response_model.__name__,
                )
            finally:
                if self.progress_queue:
                    self.progress_queue.put_nowait(True)

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
        focus: str = None,
    ) -> str:
        """Recursively summarizes content using Map-Reduce parallelization until it fits."""
        current_tokens = self.estimate_tokens([{"role": "user", "content": content}])

        if current_tokens <= target_tokens:
            return content

        if focus:
            summary_template = (
                f"Following content is too long. Summarize it into high-density facts, "
                f"prioritizing information related to: {focus}. "
                "MANDATE: You MUST preserve all exact numerical values, technical metrics, "
                "units of measure, specific dates, and proper names. "
                "Do not generalize or omit specific measurements. Only condense the narrative language.\n{chunk}"
            )
        else:
            summary_template = (
                "Following content is too long. Summarize it into high-density facts. "
                "MANDATE: You MUST preserve all exact numerical values, technical metrics, "
                "units of measure, specific dates, and proper names. "
                "Do not generalize or omit specific measurements. Only condense the narrative language.\n{chunk}"
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
            return res.summary

        summaries = await asyncio.gather(*(summarize_chunk(c) for c in chunks))
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
    ):
        """Logs the raw inputs and outputs to separate, readable files."""
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
        log_model_name: str = None,
    ) -> BaseModel:
        async with self.semaphore:
            try:
                raw_schema = response_model.model_json_schema()
                deref_schema = jsonref.replace_refs(raw_schema, proxies=False)
                deref_schema.pop("$defs", None)
                deref_schema["required"] = list(response_model.model_fields.keys())

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
                    _ensure_strict(deref_schema)
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
                if kwargs.get("stream"):
                    print_stream = os.getenv("LLM_DEBUG_STREAM", "false").lower() == "true"
                    async for chunk in response:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            delta_text = ""

                            if getattr(delta, "reasoning_content", None):
                                delta_text = delta.reasoning_content
                            elif delta.content:
                                delta_text = delta.content
                            elif getattr(delta, "tool_calls", None):
                                tc = delta.tool_calls[0]
                                if getattr(tc, "function", None) and tc.function.arguments:
                                    delta_text = tc.function.arguments

                            if delta_text:
                                content += delta_text
                                if len(content) > OUTPUT_RESERVATION * 6:
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
                                if print_stream:
                                    print(delta_text, end="", flush=True)

                    if print_stream:
                        print()
                else:
                    message = response.choices[0].message
                    content = message.content or ""
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls and len(tool_calls) > 0 and tool_calls[0].function:
                        content = tool_calls[0].function.arguments

                if not content:
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

        # --- Semaphore released: log and parse outside the concurrency gate ---
        name_for_logging = log_model_name or response_model.__name__
        await self._log_inference(current_index, messages, name_for_logging, content, step_suffix)

        try:
            if content.startswith("call:"):
                content = self._parse_unquoted_custom_syntax(content, deref_schema)
                return response_model.model_validate_json(content)

            content = repair_json(content)
            return response_model.model_validate_json(content)
        except Exception as e:
            logger.error("Pydantic Validation Failure: %s. Content: %s", e, content)
            raise
