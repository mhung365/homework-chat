# homework-chat

Scrapes a public Help Center's articles into clean Markdown, uploads them to an OpenAI
vector store via API, and keeps the store in sync with a delta-only daily job.

**Platform note:** the OpenAI Assistants API was sunset on 2026-08-26, so this project uses
the **Responses API** with the `file_search` tool and a Vector Store instead of an Assistant.
The system prompt (verbatim, unchanged) lives in [system_prompt.txt](system_prompt.txt) and
is sent as `instructions` on every call — see [ask.py](ask.py).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env   # fill in OPENAI_API_KEY; leave VECTOR_STORE_ID empty on first run
```

## Run locally

```bash
python scraper.py                              # -> articles/*.md (40 files, one per source article)
python uploader.py                              # first run: creates the vector store, saves its id to .env, uploads all files
python main.py                                  # scrape + delta-sync in one step; prints "added X, updated Y, skipped Z"
python ask.py "How do I add a YouTube video?"    # sample question with citations
```

`main.py` is the Docker entrypoint (scrape → diff against the vector store → upload only
new/changed articles). Sample delta run, then a simulated edit to prove the update path
(Zendesk content can't be edited on demand):

```bash
python main.py                                                   # added 0, updated 0, skipped 40
python main.py --simulate-update how-to-use-youtube-with-optisigns  # added 0, updated 1, skipped 39
```

## Docker

```bash
docker build -t homework-chat .
docker run --rm -e OPENAI_API_KEY=... -e VECTOR_STORE_ID=... homework-chat   # runs once, exits 0
```

## Chunking strategy

Static chunking, declared in [uploader.py](uploader.py): **800-token chunks, 400-token
overlap**. The vector store API does not return a chunk count, so `uploader.py` estimates it
locally with `tiktoken` (`cl100k_base`) from the same parameters and logs it as an estimate:
`40 files / 84 chunks (estimated: static 800 tokens, 400 overlap)`.

## Delta / state

Each vector-store file carries `slug`, `article_url`, `updated_at` and `content_hash` as
**attributes**. `main.py` compares each scraped article's hash against these attributes —
no local database or disk needed, since the container doesn't persist a disk between cron
runs. A changed article is deleted and re-uploaded (avoids duplicate/conflicting citations).

## Daily job on AWS

Runs as an ECS Fargate task (`homework-chat` cluster/family), triggered daily by EventBridge
Scheduler (`homework-chat-daily`, `rate(1 day)`). CloudWatch Logs are private to this AWS
account, so run evidence is exported into the repo instead:

- [logs/scheduled-run-2026-09-22.md](logs/scheduled-run-2026-09-22.md) — 6 runs triggered by
  EventBridge Scheduler (`startedBy: chronos-schedule/homework-chat-daily`), all exit code 0.
- [logs/manual-run-2026-09-22.md](logs/manual-run-2026-09-22.md) — first manual verification
  run on the same task definition, exit code 0.

## Sample answer

Full output: [logs/sample-answer-2026-09-22.txt](logs/sample-answer-2026-09-22.txt)
(`python ask.py "How do I add a YouTube video?"`).
Screenshot: <!-- TODO: add logs/sample-answer-screenshot.png -->

## Known limitations

- 40 scraped articles contain no `<pre>` code blocks, so the HTML→Markdown code-block path is
  only exercised on a synthetic test case, not a live article.
- The model does not always print the required `Article URL:` line itself even when
  `file_search` finds a source; `ask.py` appends it from the response's real citations instead
  of trusting the model's own text.
- The model can occasionally answer from general knowledge on clearly out-of-scope questions,
  despite "Only answer using the uploaded docs." in the system prompt (which is kept verbatim,
  per the assignment, so this isn't patched with extra instructions).
