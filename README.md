# homework-chat

OptiBot mini-clone: scrapes Help Center articles to Markdown, uploads them to an OpenAI vector store, and keeps it in sync with a daily job.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env   # add your OPENAI_API_KEY
```

## Platform notes

- The OpenAI Assistants API was sunset on 2026-08-26, so this project uses the Responses API with the `file_search` tool and a Vector Store.

_Run instructions, chunking strategy, job logs and sample-answer screenshot are added in later stories._
