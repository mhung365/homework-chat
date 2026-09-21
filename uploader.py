"""Upload Markdown files to an OpenAI vector store via the API and log files/chunks."""
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Static chunking, declared explicitly so the README can explain it and chunks can be estimated.
MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 400
CHUNKING_STRATEGY = {
    "type": "static",
    "static": {"max_chunk_size_tokens": MAX_CHUNK_TOKENS, "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS},
}
VECTOR_STORE_NAME = "optibot-docs"
UPLOAD_WORKERS = 8


def parse_frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    for line in match.group(1).splitlines() if match else []:
        key, _, value = line.partition(": ")
        meta[key] = value.strip('"')
    return meta


def estimate_chunks(text):
    """The API does not report chunk counts, so estimate from the declared static chunking.

    Each chunk holds MAX_CHUNK_TOKENS tokens and the window advances by
    MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS.
    """
    tokens = len(tiktoken.get_encoding("cl100k_base").encode(text))
    if tokens <= MAX_CHUNK_TOKENS:
        return 1
    return 1 + math.ceil((tokens - MAX_CHUNK_TOKENS) / (MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS))


def get_or_create_vector_store(client):
    """Return the configured vector store id, creating one (and saving it to .env) if unset."""
    vs_id = os.getenv("VECTOR_STORE_ID")
    if vs_id:
        return vs_id
    vs_id = client.vector_stores.create(name=VECTOR_STORE_NAME).id
    env = Path(".env")
    if env.exists() and re.search(r"^VECTOR_STORE_ID=\s*$", env.read_text(), re.M):
        env.write_text(re.sub(r"^VECTOR_STORE_ID=\s*$", f"VECTOR_STORE_ID={vs_id}", env.read_text(), flags=re.M))
    print(f"created vector store {vs_id} (saved to .env)")
    return vs_id


def upload_file(client, vector_store_id, path):
    """Upload one Markdown file with attributes used later for delta detection and citations."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    vs_file = client.vector_stores.files.upload_and_poll(
        vector_store_id=vector_store_id,
        file=path,
        attributes={
            "slug": path.stem,
            "article_url": meta["article_url"],
            "updated_at": meta["updated_at"],
            "content_hash": meta["content_hash"],
        },
        chunking_strategy=CHUNKING_STRATEGY,
    )
    if vs_file.status != "completed":
        raise RuntimeError(f"{path.name}: {vs_file.status} {vs_file.last_error}")
    return vs_file, estimate_chunks(text)


def upload_files(client, vector_store_id, paths):
    """Upload files in parallel; return (file_count, estimated_chunk_count)."""
    with ThreadPoolExecutor(UPLOAD_WORKERS) as pool:
        results = list(pool.map(lambda p: upload_file(client, vector_store_id, p), paths))
    return len(results), sum(chunks for _, chunks in results)


def clear_vector_store(client, vector_store_id):
    for vs_file in client.vector_stores.files.list(vector_store_id=vector_store_id):
        client.vector_stores.files.delete(vs_file.id, vector_store_id=vector_store_id)
        client.files.delete(vs_file.id)


if __name__ == "__main__":
    client = OpenAI()
    paths = sorted(Path(os.getenv("OUT_DIR", "articles")).glob("*.md"))
    if not paths:
        sys.exit("no Markdown files found; run scraper.py first")

    vs_id = get_or_create_vector_store(client)
    if "--reset" in sys.argv:
        clear_vector_store(client, vs_id)

    files, chunks = upload_files(client, vs_id, paths)
    counts = client.vector_stores.retrieve(vs_id).file_counts
    print(f"{files} files / {chunks} chunks (estimated: static {MAX_CHUNK_TOKENS} tokens, {CHUNK_OVERLAP_TOKENS} overlap)")
    print(f"vector store {vs_id}: {counts.completed} completed, {counts.failed} failed, {counts.in_progress} in progress")
