FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py uploader.py main.py ask.py system_prompt.txt ./

# Runs once and exits: scrape -> delta-sync the vector store -> log added/updated/skipped.
CMD ["python", "main.py"]
