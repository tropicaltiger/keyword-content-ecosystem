# Keyword Content Ecosystem — Phase 2.2

Real server-side website research engine.

### v2.1 deployment hardening
- 8 second HTTP timeout
- 75-page default to keep first live tests responsive
- Each page is fetched once instead of twice
- Browser reports a useful error when Railway returns HTML/502 instead of JSON
- Failed/skipped URLs are returned in the research JSON
- Still supports up to 200 pages when explicitly requested

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Railway

Deploy the repository and use:

```bash
gunicorn app:app
```

Railway supplies the PORT environment variable.

## Next architecture improvement

For large sites, move crawling into a background job + polling model so a 200–500 page research run is not tied to a single HTTP request.
