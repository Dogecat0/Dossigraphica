import httpx
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")

async def test_brave_search():
    if not BRAVE_SEARCH_API_KEY:
        print("Error: BRAVE_SEARCH_API_KEY not found in environment.")
        return

    query = "ASML manufacturing locations"
    print(f"Testing Brave Search for query: {query}")

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY
    }
    params = {
        "q": query,
        "count": 5
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("web", {}).get("results", [])
            print(f"Brave Search returned {len(results)} results.")
            for i, res in enumerate(results, 1):
                print(f"{i}. {res.get('title')} ({res.get('url')})")
        except Exception as e:
            print(f"Brave Search failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_brave_search())
