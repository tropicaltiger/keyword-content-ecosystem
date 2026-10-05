# Keyword Content Ecosystem (Phase 4)

Crawl a website, then tell the user, for each target keyword, whether to **optimize an existing page**,
**create a new page**, or **fix pages that compete**, plus technical issues and how the site is structured.

## Phase 4: content layer
- **Content plan tab (free, instant):** who owns each keyword, which pages should link to it, where GBP posts and FAQs should point, and a platform playbook (what is worth your time, and what is not).
- **AI writing (needs `ANTHROPIC_API_KEY`):** GBP description, posts and services; FAQs with FAQPage schema; Quora, Reddit, LinkedIn, Facebook and Pinterest content.
- **Grounded:** the writer only sees facts found on the site plus facts you type in. Missing facts become `[ADD: ...]` placeholders. Links are forced to real pages on the site. Hype words are flagged. Character limits are shown.
- Fixes: page types (service pages no longer labelled as blog posts), keyword scoring down-weights words found on every page (e.g. the city), homepage overlap no longer counts as cannibalization, links in from body vs menu shown separately.

## What changed from Phase 2.3
- **Security:** private/internal addresses are blocked (SSRF guard, re-checked on every redirect); optional access key; per-IP rate limit.
- **Polite crawling:** honors robots.txt `Disallow` and `Crawl-delay`; global request throttle; capped response size.
- **Real structure:** breadth-first crawl gives each page a click depth; internal link graph gives links in/out, orphan pages, most-linked pages.
- **Better matching:** field-weighted scoring (title, H1, URL, meta, H2, body) with exact-phrase bonus and whole-word matching (no more "art" matching "part").
- **Actionable output:** each keyword gets a verdict, evidence, a concrete to-do list, competing pages, suggested internal links, intent mismatch warnings.
- **Grouped issues** with fixes and CSV export; 404s show which page links to them; sitemap hygiene checks.
- **Fixed bugs:** `lstrip("www.")`, wrong score in the cannibalization check, duplicate HTML ids, fake progress bar, misleading "URLs discovered".
- Jobs expire and are capped in memory; jobs can be cancelled.

## Run locally
```
pip install -r requirements.txt
python app.py            # http://localhost:5000
```
To crawl a site on your own machine (localhost), set `ALLOW_PRIVATE_HOSTS=1`. **Never set it in production.**

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `APP_ACCESS_KEY` | unset | If set, the UI asks for it and the API requires `X-Access-Key` |
| `MAX_CONCURRENT_JOBS` | 2 | Crawls running at once |
| `RATE_LIMIT_PER_HOUR` | 10 | Analyses one IP can start per hour |
| `ANTHROPIC_API_KEY` | unset | Turns on AI writing. Costs money per run, so set `APP_ACCESS_KEY` too |
| `ANTHROPIC_MODEL` | claude-sonnet-5-5 | Model used for writing |
| `CONTENT_LIMIT_PER_HOUR` | 6 | Writing runs one IP can start per hour |
| `ALLOW_PRIVATE_HOSTS` | unset | Local testing only |

## Deploy on Railway
Push to GitHub and redeploy. Set `APP_ACCESS_KEY` in Railway Variables. Keep **one** gunicorn worker (jobs live in memory).

## Known limits (honest list)
- Does not run JavaScript, so pages rendered only by JS look empty.
- DNS-rebinding is a theoretical gap in the SSRF guard (host is resolved at check time and again at connect time).
- Jobs are lost on restart. For several replicas, move jobs to Redis/Postgres.
- Keyword scoring is lexical. Next step is embeddings or an LLM to judge intent and suggest missing subtopics.

## Suggested next steps
1. Save projects and re-crawl comparisons (Postgres).
2. LLM-written content briefs per keyword (outline, FAQs, internal links).
3. Competitor crawl and topic-gap comparison.
4. Google Search Console data (real queries, clicks, positions).
5. Playwright rendering for JS-heavy sites.
