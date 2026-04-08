from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import logging
from pipeline import research_pipeline
from dotenv import load_dotenv
import os

# Load environment variables from .env in the project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Local Deep Research Python Sidecar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ResearchRequest(BaseModel):
    query: str

@app.post("/api/research")
async def start_research(request: ResearchRequest):
    """
    Receives the research target and starts the pure Python asynchronous pipeline, 
    returning an EventSourceResponse (SSE stream).
    """
    logger.info(f"Received research request for query: {request.query}")
    return EventSourceResponse(research_pipeline(request.query))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
