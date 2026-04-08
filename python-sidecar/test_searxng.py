import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_searxng():
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")
    print(f"Testing SearXNG at {searxng_url}...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{searxng_url}/search",
                params={
                    "q": "NVIDIA supply chain",
                    "format": "json",
                    "engines": "google,bing,duckduckgo",
                    "language": "en-US"
                }
            )
            print(f"SearXNG status: {response.status_code}")
            if response.status_code == 200:
                results = response.json()
                print(f"SearXNG results: {len(results.get('results', []))} items found.")
            else:
                print(f"SearXNG error response: {response.text}")
    except Exception as e:
        print(f"SearXNG search failed: {e}")

if __name__ == '__main__':
    asyncio.run(test_searxng())
