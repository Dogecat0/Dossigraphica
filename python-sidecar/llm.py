import os
import litellm
from pydantic import BaseModel
from typing import Type, TypeVar, Optional, List, Any
import logging
import json
from json_repair import repair_json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables for configuration
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8081/v1/")
# The model name should match LLAMA_ARG_HF_REPO from docker-compose
LLAMA_MODEL = os.getenv("LLAMA_MODEL_REPO", "unsloth/gemma-4-E2B-it-GGUF:UD-Q8_K_XL")
LLAMA_CPP_MODEL = f"openai/{LLAMA_MODEL}"

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    """
    Client wrapper for interacting with the LLM.
    Uses strict response_format and forces schema adherence via prompts.
    """
    def __init__(self, base_url: str = LLAMA_CPP_URL, model: str = LLAMA_CPP_MODEL):
        self.base_url = base_url
        self.model = model
        litellm.set_verbose = False
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-no-key-required"
        logger.info(f"Initialized LLMClient with base_url={base_url}, model={model}")

    async def generate_structured(
        self, 
        prompt: str, 
        response_model: Type[T], 
        system_prompt: str = "You are a professional research agent."
    ) -> T:
        try:
            logger.info(f"Generating structured output for {response_model.__name__}")
            
            # Extract JSON schema for the prompt
            schema_json = json.dumps(response_model.model_json_schema(), indent=2)
            
            # Construct a high-pressure strict system prompt
            strict_system_prompt = (
                f"{system_prompt}\n\n"
                f"STRICT INSTRUCTIONS:\n"
                f"1. You MUST respond with ONLY a valid JSON object.\n"
                f"2. You MUST include ALL required fields from the schema below.\n"
                f"3. You MUST NOT add any extra fields or rename keys.\n"
                f"4. Do NOT include markdown code blocks or preamble text.\n\n"
                f"REQUIRED SCHEMA:\n{schema_json}"
            )
            
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": strict_system_prompt},
                    {"role": "user", "content": prompt},
                ],
                api_base=self.base_url,
                temperature=0.1,
                response_format=response_model, 
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty content.")

            logger.info(f"Raw content length: {len(content)}")
            
            # Final validation using Pydantic via json_repair for syntax robustness
            try:
                repaired = repair_json(content)
                return response_model.model_validate_json(repaired)
            except Exception as e:
                logger.error(f"Pydantic Validation Failure: {e}. Content: {content}")
                raise

        except Exception as e:
            logger.error(f"Structured Generation Error: {e}")
            raise

    async def generate_text(
        self, 
        prompt: str, 
        system_prompt: str = "You are a professional research agent."
    ) -> str:
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                api_base=self.base_url
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating text response: {e}")
            raise

    def estimate_tokens(self, text: str) -> int:
        try:
            return len(litellm.encode(model=self.model, text=text))
        except Exception:
            return len(text) // 4

llm = LLMClient()
