"""Ask the support assistant a question: Responses API + file_search over the vector store."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
MAX_CITATIONS = 3


def cited_article_urls(client, response, vector_store_id):
    """File citations only carry a file_id; look up its article_url attribute, in citation order."""
    file_ids = []
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            for annotation in getattr(content, "annotations", []) or []:
                if annotation.type == "file_citation" and annotation.file_id not in file_ids:
                    file_ids.append(annotation.file_id)

    urls = []
    for file_id in file_ids[:MAX_CITATIONS]:
        vs_file = client.vector_stores.files.retrieve(file_id, vector_store_id=vector_store_id)
        urls.append(vs_file.attributes["article_url"])
    return urls


def ask(client, question, vector_store_id):
    """Return the assistant's answer text, with "Article URL:" lines appended from real citations.

    The system prompt asks the model to print "Article URL:" lines itself, but it does not
    always do so even when file_search finds a source (citations are carried as annotations,
    not necessarily echoed as text). Appending them from the citations makes CAP-4 hold
    reliably instead of depending on the model's compliance.
    """
    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
    )
    text = response.output_text.strip()
    urls = cited_article_urls(client, response, vector_store_id)
    # Only skip a URL if it's already on a proper "Article URL:" line (the model sometimes
    # prints the raw link under a different label, e.g. "Reference:", which doesn't count).
    already_cited = {line.partition("Article URL:")[2].strip() for line in text.splitlines() if "Article URL:" in line}
    urls = [u for u in urls if u not in already_cited]
    if urls:
        text += "\n\n" + "\n".join(f"Article URL: {u}" for u in urls)
    return text


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How do I add a YouTube video?"
    answer = ask(OpenAI(), question, os.environ["VECTOR_STORE_ID"])
    print(f"Q: {question}\n")
    print(answer)
