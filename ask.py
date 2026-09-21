"""Ask OptiBot a question: Responses API + file_search over the vector store."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def ask(client, question, vector_store_id):
    return client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
    )


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How do I add a YouTube video?"
    response = ask(OpenAI(), question, os.environ["VECTOR_STORE_ID"])
    print(f"Q: {question}\n")
    print(response.output_text)
