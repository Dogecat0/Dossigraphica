import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_connectivity():
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")
    llama_cpp_url = os.getenv("LLAMA_CPP_URL", "http://localhost:8081/v1/")
    
    print(f"Testing SearXNG at {searxng_url}...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{searxng_url}/status")
            print(f"SearXNG status: {response.status_code}")
    except Exception as e:
        print(f"SearXNG connection failed: {e}")
        
    print(f"Testing llama.cpp at {llama_cpp_url}...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{llama_cpp_url}models")
            print(f"llama.cpp models: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"llama.cpp connection failed: {e}")

if __name__ == '__main__':
    asyncio.run(test_connectivity())
