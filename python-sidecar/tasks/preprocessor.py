import logging
import asyncio
import os
import litellm
from schemas import ResearchState, SynthesizerSchema
from llm import llm

logger = logging.getLogger(__name__)

# Load dynamic context size from environment
MAX_EXTRACT_CONTEXT = int(os.getenv("MAX_EXTRACT_CONTEXT", "12000"))

def chunk_text(text: str, model: str, chunk_size: int, overlap: int) -> list:
    """
    Splits text into chunks of roughly chunk_size tokens with overlap using litellm.
    """
    try:
        # litellm.encode/decode are useful for precision
        tokens = litellm.encode(model=model, text=text)
    except Exception as e:
        logger.warning(f"Tokenization failed for model {model}: {e}. Falling back to character estimation.")
        # Fallback to rough char estimation if encoding fails (4 chars per token)
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
            # Fallback if decode fails
            chunks.append(text[start*4 : end*4])
            
        if end >= total_tokens:
            break
        start += (chunk_size - overlap)
    return chunks

async def squeeze_chunk(chunk: str, query: str) -> list:
    """
    Uses structured output to extract relevant facts from a chunk immediately.
    Squeezes specifically for Geo-Intelligence: footprint, revenue, supply chain, risk.
    """
    prompt = (
        f"Research Query: {query}\n\n"
        f"Text Chunk Content:\n{chunk}\n\n"
        "Extract highly specific, geographically focused facts for the following modules:\n"
        "1. Corporate Footprint (HQ, manufacturing, R&D, data centers)\n"
        "2. Revenue Geography (regional segments, currency exposure)\n"
        "3. Supply Chain (manufacturing nodes, raw materials, single-point-of-failure partners)\n"
        "4. Customer Concentration (geographic footprint of revenue base)\n"
        "5. Geopolitical & Regulatory Risk (export controls, local probes, trade restrictions)\n"
        "6. Strategic Expansion/Contraction (new site openings, exiting markets)\n\n"
        "Mandate: Every geographic claim MUST include its specific source or filing context."
    )
    
    system_prompt = (
        "You are a Senior Geo-Intelligence Analyst. Your task is forensic data extraction. "
        "Filter for verifiable physical locations, regional revenue figures, and localized risks. "
        "Ignore general financial metrics and narrative fluff."
    )
    
    try:
        output = await llm.generate_structured(
            prompt=prompt,
            response_model=SynthesizerSchema,
            system_prompt=system_prompt
        )
        if output.is_useful:
            return output.extracted_facts
        return []
    except Exception as e:
        logger.error(f"Error in early semantic squeeze: {e}")
        return []

async def run_preprocessor(state: ResearchState) -> ResearchState:
    """
    Refined Preprocessor:
    1. Precision Chunking (using MAX_EXTRACT_CONTEXT).
    2. Early Semantic Squeeze (Structured extraction per chunk).
    3. State Update (Clears raw_content to keep state context-efficient).
    """
    if not state.raw_content:
        return state

    logger.info(f"Preprocessing {len(state.raw_content)} sources using MAX_EXTRACT_CONTEXT={MAX_EXTRACT_CONTEXT}.")
    
    all_extracted_facts = []
    # Use a safe concurrency limit for VRAM (Semaphore 1 for sequential extraction)
    semaphore = asyncio.Semaphore(1) 

    async def process_source(source: dict):
        content = source.get("content", "")
        url = source.get("url", "")
        
        # 1. Precision Chunking (Overlap 10%)
        overlap = int(MAX_EXTRACT_CONTEXT * 0.1)
        chunks = chunk_text(content, llm.model, MAX_EXTRACT_CONTEXT, overlap)
        
        if len(chunks) > 1:
            logger.info(f"Source {url} precision-split into {len(chunks)} chunks.")
        
        for i, chunk in enumerate(chunks):
            async with semaphore:
                # 2. Early Semantic Squeeze
                facts = await squeeze_chunk(chunk, state.user_query)
                if facts:
                    logger.info(f"Squeezed {len(facts)} facts from {url} (Part {i+1}/{len(chunks)})")
                    all_extracted_facts.extend(facts)

    # Process all sources
    await asyncio.gather(*(process_source(source) for source in state.raw_content))
    
    # 3. Update State
    state.extracted_facts = list(set(state.extracted_facts + all_extracted_facts))
    
    # Clear raw_content as the facts are now in extracted_facts
    # This ensures the 'Synthesizer' doesn't re-process the same massive blobs.
    state.raw_content = [] 
    
    logger.info(f"Preprocessing complete. Total squeezed facts: {len(all_extracted_facts)}")
    return state
