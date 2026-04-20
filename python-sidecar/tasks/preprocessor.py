import logging
import asyncio
from typing import AsyncGenerator, Union, List
import os
import litellm
from schemas import ResearchState, SynthesizerSchema, InternalFact
from llm import llm

logger = logging.getLogger(__name__)

# Load dynamic context size from environment
LLAMA_CTX_PER_REQUEST = int(os.getenv("LLAMA_CTX_PER_REQUEST", "8192"))
LLAMA_N_PARALLEL = int(os.getenv("LLAMA_N_PARALLEL", "1"))

# Standard extraction prompts used for overhead calculation
EXTRACTION_SYSTEM_PROMPT = (
    "You are a Senior Geo-Intelligence Analyst. Your task is exhaustive forensic data extraction. "
    "Categorize each fact strictly. Do not include metadata (URLs, citations) in the content.\n\n"
    "STRICT ANTI-HALLUCINATION MANDATE:\n"
    "- NEVER use generic placeholders like 'Customer A', 'Supplier 1', 'Unknown Facility', or 'Unnamed Region'.\n"
    "- If a specific, proper name for an entity is not found in the text, OMIT it entirely. Do not guess.\n"
    "- High precision is mandatory. Only extract named entities with verifiable properties."
)

EXTRACTION_USER_TEMPLATE = (
    "Research Objective: {query}\n\n"
    "Text Chunk Content:\n{chunk}\n\n"
    "Extract ALL specific, geographically focused facts that satisfy the Intelligence Requirements. Assign each to one category:\n"
    "- CORPORATE: Basic info, filing types/dates, website, sector.\n"
    "- OFFICES: Physical HQ, manufacturing, R&D, data centers, regional sites.\n"
    "- REVENUE: Regional segments, revenue totals, currency exposure, YoY growth.\n"
    "- SUPPLY_CHAIN: Foundry names, assembly sites, raw materials, logistics hubs.\n"
    "- CUSTOMERS: Major client names and their HQ locations.\n"
    "- RISKS: Export controls, trade restrictions, regulatory probes, tax policies.\n"
    "- SIGNALS: New site openings, plant closures, layoffs, major investments.\n\n"
    "Mandate: Be exhaustive. Extract as many distinct facts as possible."
)

def chunk_text(text: str, model: str, chunk_size: int, overlap: int) -> list:
    """
    Splits text into chunks of roughly chunk_size tokens with overlap using litellm.
    """
    try:
        tokens = litellm.encode(model=model, text=text)
    except Exception as e:
        logger.warning(f"Tokenization failed for model {model}: {e}. Falling back to character estimation.")
        char_chunk_size = chunk_size * 4
        char_overlap = overlap * 4
        chunks = []
        start = 0
        while start < len(text):
            end = start + char_chunk_size
            chunks.append(text[start:end])
            if end >= len(text): break
            start += (char_chunk_size - char_overlap)
        return chunks

    chunks = []
    start = 0
    total_tokens = len(tokens)
    
    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        
        try:
            chunk_text = litellm.decode(model=model, tokens=chunk_tokens)
            chunks.append(chunk_text)
        except Exception:
            chunks.append(text[start*4 : end*4])
            
        if end >= total_tokens:
            break
        start += (chunk_size - overlap)
    return chunks

async def squeeze_chunk(chunk: str, query: str, source_url: str = "") -> list:
    """
    Uses structured output to extract relevant facts from a chunk immediately.
    Uses the targeted query for maximum precision.
    """
    prompt = EXTRACTION_USER_TEMPLATE.format(query=query, chunk=chunk)
    
    try:
        output = await llm.generate_structured(
            prompt=prompt,
            response_model=SynthesizerSchema,
            system_prompt=EXTRACTION_SYSTEM_PROMPT
        )
        if output.extracted_facts:
            return [
                InternalFact(
                    reasoning=f.reasoning,
                    content=f.content, 
                    category=f.category, 
                    source_url=source_url
                )
                for f in output.extracted_facts
            ]
        return []
    except Exception as e:
        logger.error(f"Error in early semantic squeeze: {e}")
        return []

async def run_preprocessor(state: ResearchState, content_queue: asyncio.Queue | None = None) -> AsyncGenerator[Union[dict, ResearchState], None]:
    """
    Pipelinable Semantic Sieve: Consumes content from a queue (produced by extractor) 
    and handles chunking + LLM fact extraction on the fly.
    """
    # Dynamically calculate the largest safe chunk size for this specific LLM
    # Use user_query as a safe default for overhead calculation
    safe_chunk_size = llm.calculate_safe_chunk_size(
        EXTRACTION_SYSTEM_PROMPT, 
        EXTRACTION_USER_TEMPLATE.format(query=state.user_query, chunk="{chunk}"), 
        SynthesizerSchema
    )
    
    logger.info(f"Pipelined Preprocessor started. Safe Chunk Size: {safe_chunk_size}")

    all_extracted_facts = []
    semaphore = asyncio.Semaphore(LLAMA_N_PARALLEL)
    pulse_queue = asyncio.Queue()
    pending_tasks = set()

    async def process_chunk(chunk: str, query: str, url: str):
        async with semaphore:
            facts = await squeeze_chunk(chunk, query, url)
            if facts:
                all_extracted_facts.extend(facts)
            await pulse_queue.put({
                "status": "preprocessing",
                "unit": "llm",
                "message": f"Preprocessing: Squeezing chunk facts"
            })

    async def process_item(item: dict):
        """Internal helper for concurrent LLM extraction of an entire source."""
        content = item.get("content", "")
        url = item.get("url", "")
        query = item.get("query") or state.user_query
        overlap = int(safe_chunk_size * 0.1)
        
        chunks = chunk_text(content, llm.model, safe_chunk_size, overlap)
        
        # Discover units immediately for tracking
        await pulse_queue.put({
            "status": "preprocessing",
            "units_discovered": len(chunks),
            "message": f"Preprocessing: Discovered {len(chunks)} chunks for {url}"
        })

        for chunk in chunks:
            task = asyncio.create_task(process_chunk(chunk, query, url))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

    async def run_consumer():
        try:
            if content_queue:
                # Pipelined Mode: Consume from Queue
                while True:
                    item = await content_queue.get()
                    if item is None: # Sentinel
                        break
                    await process_item(item)
            else:
                # Legacy Mode: Process state.raw_content
                for item in state.raw_content:
                    await process_item(item)
                    
            if pending_tasks:
                await asyncio.gather(*pending_tasks)
        except Exception as e:
            logger.error(f"Error in preprocessor consumer: {e}")
        finally:
            await pulse_queue.put(None)

    consumer_task = asyncio.create_task(run_consumer())

    while True:
        pulse = await pulse_queue.get()
        if pulse is None:
            break
        yield pulse

    await consumer_task

    # Final Deduplication and Aggregation
    unique_facts = {}
    for f in (state.extracted_facts + all_extracted_facts):
        unique_facts[f.content] = f
    
    state.extracted_facts = list(unique_facts.values())
    state.raw_content = [] # Clear raw content to save memory
    
    logger.info(f"Pipelined Preprocessing complete. Total unique facts: {len(state.extracted_facts)}")
    yield state
