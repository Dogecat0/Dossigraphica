export const CONFIG = {
  OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL || "http://localhost:11434",
  SEARXNG_BASE_URL: process.env.SEARXNG_BASE_URL || "http://localhost:8080",
  REASONING_MODEL: process.env.REASONING_MODEL || "deepseek-r1:7b",
  STRUCTURED_MODEL: process.env.STRUCTURED_MODEL || "gemma4:e2b",
  MAX_ITERATIONS: 3,
  MAX_URLS_PER_QUERY: 5,
  MAX_SEARCH_QUERIES: 5,
  MAX_CONTEXT_TOKENS: 8000,
  OUTPUT_INTEL_DIR: "public/data/intel",
  OUTPUT_RESEARCH_DIR: "public/data/research"
};
