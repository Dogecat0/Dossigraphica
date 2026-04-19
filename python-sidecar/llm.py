import os
import asyncio
import litellm
from pydantic import BaseModel, Field
from typing import Type, TypeVar, Optional, List, Any
import logging
import json
from json_repair import repair_json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables for configuration
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8081/v1/")
LLAMA_N_PARALLEL = int(os.getenv("LLAMA_N_PARALLEL", "1"))
LLAMA_CTX_PER_REQUEST = int(os.getenv("LLAMA_CTX_PER_REQUEST", "8192"))
LLAMA_OUTPUT_RESERVATION = int(os.getenv("LLAMA_OUTPUT_RESERVATION", "2048"))
# The model name should match LLAMA_ARG_HF_REPO from docker-compose
LLAMA_MODEL = os.getenv("LLAMA_MODEL_REPO", "unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_M")
LLAMA_CPP_MODEL = f"openai/{LLAMA_MODEL}"

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
    def __init__(self, base_url: str = LLAMA_CPP_URL, model: str = LLAMA_CPP_MODEL):
        self.base_url = base_url
        self.model = model
        self.semaphore = asyncio.Semaphore(LLAMA_N_PARALLEL)
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
        
        litellm.set_verbose = False
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-no-key-required"
        logger.info(f"Initialized LLMClient with base_url={base_url}, model={model}, parallel_limit={LLAMA_N_PARALLEL}, ctx_limit={LLAMA_CTX_PER_REQUEST}")

    def _construct_messages(self, prompt: str, system_prompt: str, response_model: Type[BaseModel]) -> List[dict]:
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        strict_system_prompt = (
            f"{system_prompt}\n\n"
            f"STRICT INSTRUCTIONS:\n"
            f"1. You MUST respond with ONLY a valid JSON object.\n"
            f"2. You MUST include ALL required fields from the schema below.\n"
            f"3. You MUST NOT add any extra fields or rename keys.\n"
            f"4. Do NOT include markdown code blocks or preamble text.\n\n"
            f"REQUIRED SCHEMA:\n{schema_json}"
        )
        return [
            {"role": "system", "content": strict_system_prompt},
            {"role": "user", "content": prompt},
        ]

    async def _log_inference(self, messages: List[dict], response_model: Type[BaseModel], raw_response: str):
        """Logs the raw inputs and outputs to separate, readable files."""
        async with self.counter_lock:
            self.inference_counter += 1
            current_index = self.inference_counter
        
        base_name = f"{current_index:04d}_{response_model.__name__}"
        
        # 1. Log Input (Markdown)
        input_path = os.path.join(self.log_dir, f"{base_name}_input.md")
        system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "N/A")
        user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "N/A")
        
        input_md = (
            f"# Inference {current_index:04d} - {response_model.__name__}\n\n"
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
            
            logger.info(f"Inference logged: {base_name} (Split into MD/JSON)")
        except Exception as e:
            logger.error(f"Failed to log inference files: {e}")

    async def generate_structured(
        self, 
        prompt: str, 
        response_model: Type[T], 
        system_prompt: str = "You are a professional research agent."
    ) -> T:
        messages = self._construct_messages(prompt, system_prompt, response_model)
        total_tokens = self.estimate_tokens(messages)

        if total_tokens + LLAMA_OUTPUT_RESERVATION > LLAMA_CTX_PER_REQUEST:
            logger.warning(f"Context Overflow Imminent: Request ({total_tokens}) + Reservation ({LLAMA_OUTPUT_RESERVATION}) > Limit ({LLAMA_CTX_PER_REQUEST})")
        
        async with self.semaphore:
            try:
                logger.info(f"LLM Call: {response_model.__name__} | Tokens: {total_tokens}/{LLAMA_CTX_PER_REQUEST}")
                
                response = await litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    api_base=self.base_url,
                    temperature=0.1,
                    response_format=response_model,
                    max_tokens=LLAMA_OUTPUT_RESERVATION
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("LLM returned empty content.")

                logger.info(f"Raw content length: {len(content)}")
                
                # Log the inference
                await self._log_inference(messages, response_model, content)
                
                try:
                    repaired = repair_json(content)
                    return response_model.model_validate_json(repaired)
                except Exception as e:
                    logger.error(f"Pydantic Validation Failure: {e}. Content: {content}")
                    raise

            except Exception as e:
                logger.error(f"Structured Generation Error: {e}")
                raise

    def estimate_tokens(self, messages: List[dict]) -> int:
        """Accurate message list token counting using litellm."""
        return litellm.token_counter(model=self.model, messages=messages)

    def calculate_safe_chunk_size(self, system_prompt: str, user_prompt_template: str, response_model: Type[BaseModel]) -> int:
        """Calculates how many tokens are left for a chunk given a prompt template and schema."""
        messages = self._construct_messages(user_prompt_template.format(chunk=""), system_prompt, response_model)
        overhead = self.estimate_tokens(messages)
        safe_size = LLAMA_CTX_PER_REQUEST - overhead - LLAMA_OUTPUT_RESERVATION
        return max(512, safe_size)

    async def summarize_to_fit(self, content: str, target_tokens: int, system_prompt: str = "You are a data compression specialist.") -> str:
        """Recursively summarizes content using Map-Reduce parallelization until it fits."""
        current_tokens = self.estimate_tokens([{"role": "user", "content": content}])
        
        if current_tokens <= target_tokens:
            return content

        # Determine safe chunk size for a summary request
        summary_template = "The following content is too long. Summarize it into high-density facts:\n{chunk}"
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
