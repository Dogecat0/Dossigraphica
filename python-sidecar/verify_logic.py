import json, re, logging
from json_repair import repair_json
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any

# Setup identical schemas
STRICT_CONFIG = ConfigDict(extra='forbid', strict=True)
class PlannerSchema(BaseModel):
    model_config = STRICT_CONFIG
    reasoning: str = Field(...)
    search_queries: List[str] = Field(...)

# The logic I want to put in llm.py
def _clean_json_string(text: str) -> str:
    # 1. Strip thought tags
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    # 2. Extract from markdown code blocks if present
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    # 3. Find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        return text[start:end+1]
    return text

def _map_hallucinated_keys(data: Any, reasoning_content: Optional[str] = None) -> dict:
    if not isinstance(data, dict): return data
    # Map common hallucinated keys
    key_map = {'queries': 'search_queries', 'search_items': 'search_queries'}
    for h, r in key_map.items():
        if h in data and r not in data: 
            data[r] = data[h]
            # DELETE the extra key to satisfy ConfigDict(extra='forbid')
            del data[h]
    # Ensure reasoning exists
    if 'reasoning' not in data:
        data['reasoning'] = reasoning_content or 'Reasoning extracted from model.'
    return data

# --- TEST CASE ---
# This is EXACTLY what your LFM 2.5 1.2B model returned in the curl test
raw_content = """

```json
{
  "queries": [
    "NVIDIA supply chain partnerships",
    "NVIDIA semiconductor production",
    "NVIDIA sustainability initiatives"
  ]
}
```
"""
# In litellm message object, reasoning_content is usually a separate attribute
raw_reasoning = "Thinking: I should provide 3 search queries..."

print('--- VERIFICATION START ---')
cleaned = _clean_json_string(raw_content)
print(f'Step 1: Cleaned -> {cleaned}')

repaired = repair_json(cleaned)
print(f'Step 2: Repaired -> {repaired}')

parsed = json.loads(repaired)
fixed = _map_hallucinated_keys(parsed, raw_reasoning)
print(f'Step 3: Mapped -> {fixed}')

validated = PlannerSchema.model_validate(fixed)
print(f'Step 4: Pydantic Result -> {validated}')
print('--- VERIFICATION SUCCESS ---')
