import os
import asyncio
from datetime import datetime
import litellm
from pydantic import BaseModel, Field, create_model
from typing import Type, TypeVar, Optional, List, Any, Dict
import logging
import json
import jsonref
from json_repair import repair_json
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from pydantic import ValidationError
from litellm.exceptions import (
    RateLimitError,
    ServiceUnavailableError,
    APIConnectionError,
    InternalServerError,
    Timeout
)

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

def before_sleep_log_model(logger_obj, log_level):
    def log_it(retry_state):
        if retry_state.outcome.failed:
            ex = retry_state.outcome.exception()
            self_instance = retry_state.args[0]
            verb, value = "raised", f"{type(ex).__name__}: {ex}"
            logger_obj.log(
                log_level,
                f"Retrying structured generation (attempt {retry_state.attempt_number}) for model '{self_instance.model}' "
                f"in {retry_state.next_action.sleep} seconds as it {verb} {value}"
            )
    return log_it

# Provider configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local").lower()

# Local Llama.cpp configuration
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8081/v1/")
LLAMA_N_PARALLEL = int(os.getenv("LLAMA_N_PARALLEL", "1"))
LLAMA_CTX_PER_REQUEST = int(os.getenv("LLAMA_CTX_PER_REQUEST", "8192"))
LLAMA_MODEL = os.getenv("LLAMA_MODEL_REPO", "unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_M")

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-3.1-flash-lite-preview")
GEMINI_N_PARALLEL = int(os.getenv("GEMINI_N_PARALLEL", "10"))
GEMINI_CTX_PER_REQUEST = int(os.getenv("GEMINI_CTX_PER_REQUEST", "32768")) # 1M default for Flash

# Featherless configuration
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "moonshotai/Kimi-K2.6")
FEATHERLESS_N_PARALLEL = int(os.getenv("FEATHERLESS_N_PARALLEL", "1"))
FEATHERLESS_CTX_PER_REQUEST = int(os.getenv("FEATHERLESS_CTX_PER_REQUEST", "32768"))

# Output and safety configuration
LLAMA_OUTPUT_RESERVATION = int(os.getenv("LLAMA_OUTPUT_RESERVATION", "4096"))
LLAMA_SAFETY_BUFFER = 64
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_OUTPUT_MODE = os.getenv("LLM_OUTPUT_MODE", "multi-shot").lower()


# Active configuration selection
if LLM_PROVIDER == "gemini":
    ACTIVE_MODEL = GEMINI_MODEL
    ACTIVE_BASE_URL = None
    ACTIVE_N_PARALLEL = GEMINI_N_PARALLEL
    ACTIVE_CTX_LIMIT = GEMINI_CTX_PER_REQUEST
    if GEMINI_API_KEY:
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    logger.info(f"LLM Provider: GEMINI (model={ACTIVE_MODEL})")
elif LLM_PROVIDER == "featherless":
    ACTIVE_MODEL = f"openai/{FEATHERLESS_MODEL}"
    ACTIVE_BASE_URL = FEATHERLESS_BASE_URL
    ACTIVE_N_PARALLEL = FEATHERLESS_N_PARALLEL
    ACTIVE_CTX_LIMIT = FEATHERLESS_CTX_PER_REQUEST
    if FEATHERLESS_API_KEY:
        os.environ["OPENAI_API_KEY"] = FEATHERLESS_API_KEY
    logger.info(f"LLM Provider: FEATHERLESS (model={ACTIVE_MODEL}, url={ACTIVE_BASE_URL})")
else:
    ACTIVE_MODEL = f"openai/{LLAMA_MODEL}"
    ACTIVE_BASE_URL = LLAMA_CPP_URL
    ACTIVE_N_PARALLEL = LLAMA_N_PARALLEL
    ACTIVE_CTX_LIMIT = LLAMA_CTX_PER_REQUEST
    logger.info(f"LLM Provider: LOCAL (model={ACTIVE_MODEL}, url={ACTIVE_BASE_URL})")


T = TypeVar("T", bound=BaseModel)

class SummarySchema(BaseModel):
    reasoning: str = Field(..., description="Analysis of the source material before summarization.")
    summary: str = Field(..., description="A high-density summary of the provided information, preserving all exact numbers, coordinates, and citations.")

class LLMClient:
    """
    Client wrapper for interacting with the LLM.
    Uses strict response_format and forces schema adherence via prompts.
    Centralized semaphore enforces LLAMA_N_PARALLEL across all tasks.
    """
    def __init__(self, base_url: str = ACTIVE_BASE_URL, model: str = ACTIVE_MODEL):
        self.base_url = base_url
        self.model = model
        self.semaphore = asyncio.Semaphore(ACTIVE_N_PARALLEL)
        self.counter_lock = asyncio.Lock()
        self.inference_counter = 0
        self.log_dir = os.path.join(os.path.dirname(__file__), "logs", "inference")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Initialize inference counter from existing logs so replay won't overwrite
        max_idx = 0
        if os.path.exists(self.log_dir):
            for f in os.listdir(self.log_dir):
                import re
                match = re.match(r'^(\d+)_', f)
                if match:
                    idx = int(match.group(1))
                    if idx > max_idx:
                        max_idx = idx
        self.inference_counter = max_idx
        
        # Suppress LiteLLM internal logging (completion messages, etc.) unless there is an error
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        litellm.set_verbose = False
        
        if not os.getenv("OPENAI_API_KEY") and not ACTIVE_BASE_URL:
            # Only set dummy key if not using a custom base_url (local llama.cpp needs it sometimes but Gemini doesn't)
            # Actually Gemini needs GEMINI_API_KEY which we already set.
            pass
        elif not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-no-key-required"
            
        # Force register model capabilities if using Featherless
        if LLM_PROVIDER == "featherless":
            litellm.register_model({
                self.model: {
                    "supports_function_calling": True,
                    "supports_parallel_function_calling": False
                }
            })
            
        logger.info(f"Initialized LLMClient with provider={LLM_PROVIDER}, model={model}, parallel_limit={ACTIVE_N_PARALLEL}, ctx_limit={ACTIVE_CTX_LIMIT}")

    def get_safe_input_limit(self) -> int:
        """Absolute maximum input tokens allowed after reservation and safety buffer."""
        return ACTIVE_CTX_LIMIT - LLAMA_OUTPUT_RESERVATION - LLAMA_SAFETY_BUFFER

    def _parse_unquoted_custom_syntax(self, content: str, deref_schema: dict) -> str:
        """
        Parses Hermes-style unquoted tool calls (e.g. call:Name{key:val,with,commas}) 
        by dynamically anchoring on the known schema keys to avoid splitting on internal commas.
        """
        import re
        import json
        
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
        # Lookahead: match everything until the next known key or end of string
        regex = rf"({keys_pattern}):(.*?)(?=,(?:{keys_pattern}):|$)"
        
        match = re.search(r"call:\w+\{(.*)\}", content, re.DOTALL)
        if not match:
            return content
            
        inner = match.group(1)
        
        # Array payload handling (e.g. {extracted_facts:[{...},{...}]})
        list_match = re.search(r'\[(.*)\]', inner, re.DOTALL)
        if list_match:
            top_key_match = re.search(r'(\w+):\[', inner)
            top_key = top_key_match.group(1) if top_key_match else list(schema_keys)[0]
            
            list_content = list_match.group(1)
            objects = re.findall(r'\{(.*?)\}', list_content, re.DOTALL)
            
            parsed_objects = []
            for obj in objects:
                fields = re.finditer(regex, obj, re.DOTALL)
                parsed_obj = {f.group(1): f.group(2).strip().strip('"').strip("'") for f in fields}
                if parsed_obj:
                    parsed_objects.append(parsed_obj)
            return json.dumps({top_key: parsed_objects})
        else:
            # Flat object handling
            fields = re.finditer(regex, inner, re.DOTALL)
            parsed_obj = {f.group(1): f.group(2).strip().strip('"').strip("'") for f in fields}
            return json.dumps(parsed_obj) if parsed_obj else content



    def _construct_messages(self, prompt: str, system_prompt: str, response_model: Type[BaseModel], function_name: str | None = None) -> List[dict]:
        raw_schema = response_model.model_json_schema()
        deref_schema = jsonref.replace_refs(raw_schema, proxies=False)
        deref_schema.pop("$defs", None)
        
        schema_json = json.dumps(deref_schema, indent=2)
        now = datetime.now().isoformat()

        # Instruction for which function to call (only for tool-based providers)
        call_instruction = f"5. You MUST call the function `{function_name}` to submit your result.\n" if (function_name) else ""

        strict_system_prompt = (
            f"{system_prompt}\n\n"
            f"CURRENT_TIME: {now}\n\n"
            f"STRICT INSTRUCTIONS:\n"
            f"1. You MUST respond with ONLY a valid JSON object.\n"
            f"2. You MUST NOT add any extra fields or rename keys.\n"
            f"3. All keys and string values MUST be enclosed in double quotes (\"). This is MANDATORY, especially if the text contains commas or periods.\n"
            f"4. If a property is nullable and you have no data, output `null`. If a property is required and NOT nullable, you MUST provide a valid value.\n"
            f"{call_instruction}"
            f"Do NOT include markdown code blocks or preamble text.\n\n"
            f"REQUIRED SCHEMA:\n{schema_json}"
        )
        return [
            {"role": "system", "content": strict_system_prompt},
            {"role": "user", "content": prompt},
        ]

    async def _log_inference(self, current_index: int, messages: List[dict], model_name: str, raw_response: str, step_suffix: str = ""):
        """Logs the raw inputs and outputs to separate, readable files."""
        base_name = f"{current_index:04d}_{model_name}{step_suffix}"
        
        # 1. Log Input (Markdown)
        input_path = os.path.join(self.log_dir, f"{base_name}_input.md")
        system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "N/A")
        user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "N/A")
        
        input_md = (
            f"# Inference {current_index:04d} - {model_name}{step_suffix}\n\n"
            f"**Model:** `{self.model}`\n\n"
            f"## System Prompt\n\n{system_prompt}\n\n"
            f"## User Prompt\n\n{user_prompt}\n"
        )
        
        # 2. Log Output (JSON Indented) and Reasoning (Markdown)
        output_path = os.path.join(self.log_dir, f"{base_name}_output.json")
        reasoning_path = os.path.join(self.log_dir, f"{base_name}_reasoning.md")
        
        parsed_json = None
        try:
            # Try to repair and parse to get a pretty version and extract reasoning
            repaired = repair_json(raw_response)
            parsed_json = json.loads(repaired)
            formatted_output = json.dumps(parsed_json, indent=2)
        except Exception:
            formatted_output = raw_response

        try:
            # Write Input MD
            with open(input_path, "w") as f:
                f.write(input_md)
            
            # Write Output JSON
            with open(output_path, "w") as f:
                f.write(formatted_output)
            
            # Write Reasoning MD if available
            if parsed_json and isinstance(parsed_json, dict) and "reasoning" in parsed_json:
                with open(reasoning_path, "w") as f:
                    f.write(f"# Reasoning - {base_name}\n\n{parsed_json['reasoning']}\n")
            
            logger.debug(f"Inference logged: {base_name} (Split into MD/JSON)")
        except Exception as e:
            logger.error(f"Failed to log inference files: {e}")

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=2, min=15, max=120),
        retry=(
            retry_if_exception_type(RateLimitError) |
            retry_if_exception_type(ServiceUnavailableError) |
            retry_if_exception_type(APIConnectionError) |
            retry_if_exception_type(InternalServerError) |
            retry_if_exception_type(Timeout) |
            retry_if_exception_type(ValidationError) |
            retry_if_exception_type(ValueError)
        ),
        before_sleep=before_sleep_log_model(logger, logging.WARNING),
        reraise=True
    )
    async def _generate_single_field(self, messages: List[dict], response_model: Type[BaseModel], current_index: int, step_suffix: str, log_model_name: str = None) -> BaseModel:
        total_tokens = self.estimate_tokens(messages)
        
        async with self.semaphore:
            try:
                # Manually dereference schema
                raw_schema = response_model.model_json_schema()
                deref_schema = jsonref.replace_refs(raw_schema, proxies=False)
                deref_schema.pop("$defs", None)
                deref_schema["required"] = list(response_model.model_fields.keys())
                
                logger.debug(f"LLM Call: {response_model.__name__} | Tokens: {total_tokens}/{ACTIVE_CTX_LIMIT} | Temp: {LLM_TEMPERATURE}")
                
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "api_base": self.base_url,
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLAMA_OUTPUT_RESERVATION,
                    "add_function_to_prompt": False,
                    "num_retries": 0,
                    "stream": True
                }

                if LLM_PROVIDER == "gemini":
                    kwargs["response_format"] = {
                        "type": "json_object",
                        "response_schema": deref_schema
                    }
                elif LLM_PROVIDER == "featherless":
                    # For featherless or non-native models, we use tools but rely on 
                    kwargs["tools"] = [{
                        "type": "function",
                        "function": {
                            "name": response_model.__name__,
                            "description": "Submit structured research data.",
                            "parameters": deref_schema
                        }
                    }]
                    kwargs["tool_choice"] = {
                        "type": "function",
                        "function": {"name": response_model.__name__}
                    }
                else:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": field_model.__name__,
                            "strict": True,
                            "schema": deref_schema
                        }
                    }

                response = await litellm.acompletion(**kwargs)
                
                # Handle both Streaming and Static responses
                content = ""
                if kwargs.get("stream"):
                    print_stream = os.getenv("LLM_DEBUG_STREAM", "false").lower() == "true"
                    async for chunk in response:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            delta_text = ""
                            is_reasoning_field = False
                            
                            # Support DeepSeek's explicit reasoning_content field
                            if getattr(delta, "reasoning_content", None):
                                delta_text = delta.reasoning_content
                                is_reasoning_field = True
                            elif delta.content:
                                delta_text = delta.content
                            elif getattr(delta, "tool_calls", None):
                                if getattr(delta.tool_calls[0], "function", None) and delta.tool_calls[0].function.arguments:
                                    delta_text = delta.tool_calls[0].function.arguments
                            
                            if delta_text:
                                content += delta_text
                                # Print delta to screen if enabled (Note: outputs will interlace if running parallel requests)
                                if print_stream:
                                    print(delta_text, end="", flush=True)
                    
                    if print_stream:
                        print() # Ensure newline after stream completes
                else:
                    message = response.choices[0].message
                    content = message.content or ""
                    
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls and len(tool_calls) > 0 and tool_calls[0].function:
                        # Prefer tool call arguments if present
                        content = tool_calls[0].function.arguments
                
                # Final check: if LiteLLM didn't parse but the content looks like a tool call, 
                # we'll let repair_json handle it.
                if not content:
                    raise ValueError("LLM returned empty content and no tool calls.")

                logger.debug(f"Raw content length: {len(content)}")
                
                # Log the inference
                name_for_logging = log_model_name or response_model.__name__
                await self._log_inference(current_index, messages, name_for_logging, content, step_suffix)
                
                try:
                    # Deterministic architectural handler for non-standard Hermes/tool-call syntax
                    if content.startswith("call:"):
                        content = self._parse_unquoted_custom_syntax(content, deref_schema)
                        return response_model.model_validate_json(content)

                    # Coerce minor JSON format errors
                    content = repair_json(content)
                    return response_model.model_validate_json(content)
                except Exception as e:
                    logger.error(f"Pydantic Validation Failure: {e}. Content: {content}")
                    raise ValidationError.from_exception_data(title=response_model.__name__, line_errors=[]) from e

            except (RateLimitError, ServiceUnavailableError, APIConnectionError, InternalServerError, Timeout, ValueError, ValidationError) as e:
                logger.error(f"Structured Generation attempt failed for model '{self.model}': {type(e).__name__}: {e}")
                raise
            except Exception as e:
                logger.critical(f"Unrecoverable Structured Generation Error for model '{self.model}': {type(e).__name__}: {e}")
                raise


    async def generate_structured(
        self, 
        prompt: str, 
        response_model: Type[T], 
        system_prompt: str = "You are a professional research agent."
    ) -> T:
        async with self.counter_lock:
            self.inference_counter += 1
            current_index = self.inference_counter

        if LLM_OUTPUT_MODE == "one-shot":
            messages = self._construct_messages(prompt, system_prompt, response_model)
            return await self._generate_single_field(messages, response_model, current_index, "")

        # Multi-shot generation
        current_output = {}
        for i, (field_name, field_info) in enumerate(response_model.model_fields.items(), start=1):
            # Create a dynamic Pydantic model for just this field
            annotation = field_info.annotation
            FieldModel = create_model(field_name, **{field_name: (annotation, Field(..., description=field_info.description))})
            
            # Append context to the prompt
            multi_shot_prompt = (
                f"{prompt}\n\n"
                f"--- MULTI-SHOT GENERATION PROGRESS ---\n"
                f"We are generating the final JSON object field by field.\n"
                f"Current output so far:\n```json\n{json.dumps(current_output, indent=2)}\n```\n\n"
                f"Your task is to generate the next field: `{field_name}`."
            )
            
            # The LLM receives the full schema for context in the prompt, while the tool is focused on FieldModel.
            messages = self._construct_messages(multi_shot_prompt, system_prompt, response_model, function_name=field_name)
            
            partial_result = await self._generate_single_field(
                messages, 
                FieldModel, 
                current_index, 
                f"_{i:02d}",
                log_model_name=response_model.__name__
            )
            
            field_value = getattr(partial_result, field_name)
            current_output[field_name] = field_value
            
        return response_model(**current_output)

    def estimate_tokens(self, messages: List[dict]) -> int:
        """Accurate message list token counting using litellm."""
        return litellm.token_counter(model=self.model, messages=messages)

    def calculate_safe_chunk_size(self, system_prompt: str, user_prompt_template: str, response_model: Type[BaseModel]) -> int:
        """Calculates how many tokens are left for a chunk given a prompt template and schema."""
        messages = self._construct_messages(user_prompt_template.format(chunk=""), system_prompt, response_model)
        overhead = self.estimate_tokens(messages)
        
        # The safe size is the remaining space within the safe input limit after accounting for overhead.
        safe_size = self.get_safe_input_limit() - overhead
        
        return max(512, safe_size)

    async def summarize_to_fit(self, content: str, target_tokens: int, system_prompt: str = "You are a data compression specialist.") -> str:
        """Recursively summarizes content using Map-Reduce parallelization until it fits."""
        # Use a single user message to estimate the content's token footprint.
        # This includes a small role/message overhead which keeps us conservative.
        current_tokens = self.estimate_tokens([{"role": "user", "content": content}])
        
        if current_tokens <= target_tokens:
            return content

        # Determine safe chunk size for a summary request
        summary_template = "Following content is too long. Summarize it into high-density facts, keep all information, only condense the language used:\n{chunk}"
        safe_chunk_tokens = self.calculate_safe_chunk_size(system_prompt, summary_template, SummarySchema)
        
        logger.info(f"Map-Reduce Summary: {current_tokens} tokens -> target {target_tokens}. Chunking at {safe_chunk_tokens}.")

        # Split content into chunks
        try:
            tokens = litellm.encode(model=self.model, text=content)
            chunks = []
            for i in range(0, len(tokens), safe_chunk_tokens):
                chunk_tokens = tokens[i:i + safe_chunk_tokens]
                chunks.append(litellm.decode(model=self.model, tokens=chunk_tokens))
        except Exception:
            # Fallback to character splitting if tokenization fails
            char_size = safe_chunk_tokens * 4
            chunks = [content[i:i + char_size] for i in range(0, len(content), char_size)]

        async def summarize_chunk(chunk_text: str) -> str:
            prompt = summary_template.format(chunk=chunk_text)
            res = await self.generate_structured(prompt, SummarySchema, system_prompt)
            return res.summary

        # Parallel map
        summaries = await asyncio.gather(*(summarize_chunk(c) for c in chunks))
        combined_summary = "\n\n".join(summaries)
        
        # Recursive reduce
        return await self.summarize_to_fit(combined_summary, target_tokens, system_prompt)

llm = LLMClient()
