import logging
import asyncio
import os
import litellm
from schemas import ResearchState, SynthesizerSchema, InternalFact, INTELLIGENCE_GOALS
from llm import llm

logger = logging.getLogger(__name__)

# Load dynamic context size from environment
LLAMA_CTX_PER_REQUEST = int(os.getenv("LLAMA_CTX_PER_REQUEST", "8192"))
LLAMA_N_PARALLEL = int(os.getenv("LLAMA_N_PARALLEL", "1"))

# Standard extraction prompts used for overhead calculation
EXTRACTION_SYSTEM_PROMPT = (
    "You are a Senior Geo-Intelligence Analyst. Your task is exhaustive forensic data extraction. "
    "Your goal is to extract EVERY possible geographic fact, location, revenue figure, and localized risk. "
    "Be greedy: if a sentence contains a physical site, a regional percentage, or a local regulation, extract it. "
    "Categorize each fact strictly. Do not include metadata (URLs, citations) in the content."
)

EXTRACTION_USER_TEMPLATE = (
    "Research Objective: {query}\n\n"
    "Intelligence Requirements:\n" + INTELLIGENCE_GOALS + "\n\n"
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

async def run_preprocessor(state: ResearchState) -> ResearchState:
    """
    Refined Preprocessor:
    1. Dynamic Safe Chunking (based on longest query).
    2. Early Semantic Squeeze (using Targeted Search Queries).
    3. State Update & Deduplication.
    """
    if not state.raw_content:
        return state

    # Find the longest query among the sources to calculate a conservative safe chunk size
    # This prevents context overflow even if different sources have different query lengths.
    queries = [s.get("query") for s in state.raw_content if s.get("query")]
    reference_query = max(queries, key=len) if queries else state.user_query

    safe_chunk_size = llm.calculate_safe_chunk_size(
        EXTRACTION_SYSTEM_PROMPT, 
        EXTRACTION_USER_TEMPLATE.format(query=reference_query, chunk="{chunk}"), 
        SynthesizerSchema
    )
    
    logger.info(f"Preprocessing {len(state.raw_content)} sources. Safe Chunk Size: {safe_chunk_size} (Reference Query: '{reference_query[:50]}...')")

    all_extracted_facts = []
    
    async def process_source(source: dict):
        content = source.get("content", "")
        url = source.get("url", "")
        # Use the specific query that found this source
        targeted_query = source.get("query") or state.user_query
        
        # 1. Precision Chunking (Overlap 10%)
        overlap = int(safe_chunk_size * 0.1)
        chunks = chunk_text(content, llm.model, safe_chunk_size, overlap)
        
        if len(chunks) > 1:
            logger.info(f"Source {url} precision-split into {len(chunks)} chunks.")
        
        async def process_chunk(i, chunk):
            facts = await squeeze_chunk(chunk, targeted_query, url)
            if facts:
                logger.info(f"Squeezed {len(facts)} facts from {url} using query '{targeted_query}' (Part {i+1}/{len(chunks)})")
                return facts
            return []

        results = await asyncio.gather(*(process_chunk(i, chunk) for i, chunk in enumerate(chunks)))
        for facts in results:
            if facts:
                all_extracted_facts.extend(facts)

    # Process all sources in parallel
    await asyncio.gather(*(process_source(source) for source in state.raw_content))
    
    # 3. Update State (Deduplicate based on content)
    unique_facts = {}
    for f in (state.extracted_facts + all_extracted_facts):
        unique_facts[f.content] = f
    
    state.extracted_facts = list(unique_facts.values())
    state.raw_content = [] 
    
    logger.info(f"Preprocessing complete. Total unique facts: {len(state.extracted_facts)}")
    return state
