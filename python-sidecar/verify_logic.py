import asyncio
from llm import llm
from pydantic import BaseModel

class TestSchema(BaseModel):
    response: str

async def main():
    print("Testing LLM structured generation...")
    try:
        response = await llm.generate_structured(
            "Hi, what model are you?",
            response_model=TestSchema
        )
        print(f"Response: {response.response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
