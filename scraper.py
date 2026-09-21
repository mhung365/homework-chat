"""Fetch Help Center articles from the Zendesk API and write clean Markdown files.

Each file `<slug>.md` starts with frontmatter (article_url, title, updated_at,
content_hash) followed by an `Article URL:` line so the assistant can cite it.
"""
import hashlib
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markdownify import markdownify

load_dotenv()

BASE_URL = os.getenv("ZENDESK_BASE_URL", "https://support.optisigns.com").rstrip("/")
ARTICLE_LIMIT = int(os.getenv("ARTICLE_LIMIT", "40"))
# Always included so the sample question ("How do I add a YouTube video?") has its source article.
PINNED_IDS = {"360051014713"}  # How to Use YouTube with OptiSigns
OUT_DIR = Path(os.getenv("OUT_DIR", "articles"))


def fetch_articles(limit=ARTICLE_LIMIT):
    """Return up to `limit` published articles.

    Selection is deterministic (pinned ids, then lowest ids) so reruns pick the
    same set and the delta job doesn't see churn from Zendesk reordering.
    """
    url = f"{BASE_URL}/api/v2/help_center/en-us/articles.json?per_page=100"
    articles = []
    while url:
        for attempt in range(5):
            resp = requests.get(url, timeout=30)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
            resp.raise_for_status()
            break
        else:
            raise RuntimeError(f"Zendesk rate limit not clearing for {url}")
        data = resp.json()
        articles += [a for a in data["articles"] if not a["draft"] and a["body"]]
        url = data["next_page"]

    pinned = [a for a in articles if str(a["id"]) in PINNED_IDS]
    rest = sorted((a for a in articles if str(a["id"]) not in PINNED_IDS), key=lambda a: int(a["id"]))
    return (pinned + rest)[:limit]


def html_to_markdown(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # Empty anchors like <a name="x"></a> are in-page targets, useless in Markdown.
    for a in soup.find_all("a"):
        if not a.get_text(strip=True) and not a.find("img"):
            a.decompose()
        elif a.get("href", "").startswith("#") or not a.get("href"):
            a.unwrap()
    # Bold/italic inside headings just produces "## **Title**".
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
        for inline in heading.find_all(["strong", "b", "em", "i"]):
            inline.unwrap()
    # One-column tables are callout boxes (often with an empty header row), not data tables.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if all(len(r.find_all(["td", "th"])) <= 1 for r in rows):
            quote = soup.new_tag("blockquote")
            for cell in table.find_all(["td", "th"]):
                if cell.get_text(strip=True) or cell.find("img"):
                    wrapper = soup.new_tag("p")
                    wrapper.extend(list(cell.contents))
                    quote.append(wrapper)
            table.replace_with(quote)
    # Embedded videos: keep the link instead of dropping the content.
    for frame in soup.find_all("iframe"):
        src = frame.get("src")
        if src and src.startswith("//"):
            src = "https:" + src
        if src:
            link = soup.new_tag("a", href=src)
            link.string = src
            frame.replace_with(link)
        else:
            frame.decompose()

    md = markdownify(str(soup), heading_style="ATX", bullets="-", code_language="", strip=["span", "font", "u"])
    md = md.replace("\xa0", " ")
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def slugify(article):
    # html_url ends in "<id>-<Title-Words>"; reuse it so filenames match the live URL.
    tail = article["html_url"].rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"^\d+-?", "", tail.split("?")[0]).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or str(article["id"])


def render(article):
    """Return the full file text (frontmatter + body) and its content hash."""
    url = article["html_url"]
    body = f"# {article['title'].strip()}\n\nArticle URL: {url}\n\n{html_to_markdown(article['body'])}\n"
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    title = article["title"].strip().replace('"', '\\"')
    frontmatter = (
        "---\n"
        f"article_url: {url}\n"
        f'title: "{title}"\n'
        f"updated_at: {article['updated_at']}\n"
        f"content_hash: {content_hash}\n"
        "---\n\n"
    )
    return frontmatter + body, content_hash


def scrape(out_dir=OUT_DIR, limit=ARTICLE_LIMIT):
    """Write one Markdown file per article; return a list of dicts describing them."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()

    results, seen = [], set()
    for article in fetch_articles(limit):
        slug = slugify(article)
        if slug in seen:
            slug = f"{slug}-{article['id']}"
        seen.add(slug)
        text, content_hash = render(article)
        path = out_dir / f"{slug}.md"
        path.write_text(text, encoding="utf-8")
        results.append(
            {
                "id": str(article["id"]),
                "slug": slug,
                "path": path,
                "article_url": article["html_url"],
                "updated_at": article["updated_at"],
                "content_hash": content_hash,
            }
        )
    return results


if __name__ == "__main__":
    files = scrape()
    print(f"scraped {len(files)} articles into {OUT_DIR}/")
