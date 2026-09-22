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
# runs once, exits 0
docker run --rm \
  -e OPENAI_API_KEY="$(grep OPENAI_API_KEY .env | cut -d= -f2)" \
  -e VECTOR_STORE_ID="$(grep VECTOR_STORE_ID .env | cut -d= -f2)" \
  homework-chat:local
echo "exit code: $?"   
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
Screenshot:  
![Architecture](./images/Screenshot%202026-09-22%20at%2014.59.47.png)

## Known limitations

- **No automated tests yet.** I ran out of time to write a test suite; the pipeline was
verified manually instead (local runs, the `--simulate-update` delta check, and the
scheduled ECS runs linked above).

