"""Scrape Help Center articles and sync them into the OpenAI vector store, delta-only.

Compares each article's content_hash against the hash stored in that file's vector-store
attributes (see stack.md: state lives in the vector store, not on local disk, because the
cron container doesn't keep a disk between runs). Logs "added X, updated Y, skipped Z".
"""
import sys

from openai import OpenAI

from scraper import scrape
from uploader import get_or_create_vector_store, upload_file


def existing_files_by_slug(client, vector_store_id):
    """Map slug -> current VectorStoreFile, from each file's stored attributes."""
    return {f.attributes["slug"]: f for f in client.vector_stores.files.list(vector_store_id=vector_store_id)}


def delete_file(client, vector_store_id, file_id):
    client.vector_stores.files.delete(file_id, vector_store_id=vector_store_id)
    client.files.delete(file_id)


def sync(client, vector_store_id, articles, simulate_update_slug=None):
    """Upload only new/changed articles; return counts as a dict."""
    if simulate_update_slug:
        # Demo-only hook (CAP-6 acceptance requires showing an "updated 1" run). Zendesk is a
        # third-party source we can't edit on demand, so this flips one article's hash instead
        # of editing content, to prove the delta path without touching real data.
        target = next((a for a in articles if a["slug"] == simulate_update_slug), None)
        if target is None:
            sys.exit(f"--simulate-update: no article with slug {simulate_update_slug!r}")
        target["content_hash"] = "0" * 64
        print(f"[simulated] treating {simulate_update_slug} as modified for this run")

    existing = existing_files_by_slug(client, vector_store_id)
    counts = {"added": 0, "updated": 0, "skipped": 0}
    for article in articles:
        prior = existing.get(article["slug"])
        if prior is None:
            upload_file(client, vector_store_id, article["path"])
            counts["added"] += 1
        elif prior.attributes.get("content_hash") != article["content_hash"]:
            delete_file(client, vector_store_id, prior.id)
            upload_file(client, vector_store_id, article["path"])
            counts["updated"] += 1
        else:
            counts["skipped"] += 1
    return counts


if __name__ == "__main__":
    simulate_update_slug = None
    if "--simulate-update" in sys.argv:
        simulate_update_slug = sys.argv[sys.argv.index("--simulate-update") + 1]

    client = OpenAI()
    articles = scrape()
    vector_store_id = get_or_create_vector_store(client)
    counts = sync(client, vector_store_id, articles, simulate_update_slug)
    print(f"added {counts['added']}, updated {counts['updated']}, skipped {counts['skipped']}")
