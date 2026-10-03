# Keyword Content Ecosystem — Phase 2.2

This is the first real backend-connected Website Research Engine.

## Run locally

Python 3.10+:

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Railway

Upload this folder/repository to Railway. Railway can detect Python. The start command is:

```bash
gunicorn app:app
```

## What it currently does

- Accepts a website URL and 1–3 keywords.
- Fetches robots.txt and common sitemap locations.
- Recursively parses sitemap indexes.
- Uses sitemap URLs first, then discovers same-domain internal links.
- Normalizes URLs and strips common tracking parameters.
- Skips common non-HTML assets.
- Extracts title, meta description, H1/H2, canonical, visible text and word count.
- Flags missing title/H1/meta, thin pages and multiple H1s.
- Classifies pages into broad types.
- Scores pages against each supplied keyword.
- Selects an existing target, flags possible cannibalization, or recommends CREATE.
- Groups analyzed pages by page type.
- Exports the research JSON.

## Deliberate limitations in 2.2

No AI generation, SERP scraping, competitor discovery, backlink data or Google Search Console integration yet. Those should be added only after the crawling/research output is validated on real client sites.
