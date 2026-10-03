# Keyword Content Ecosystem — Phase 2.3

Background-crawler architecture for Railway.

## Why
The previous version crawled the whole site inside `/api/analyze`. Gunicorn killed that synchronous request after its worker timeout. This version returns a job ID immediately and crawls in a background thread.

## Flow
POST `/api/analyze` → job ID → background crawler → GET `/api/jobs/{id}` → dashboard results.

## Current limits
- Default: 75 pages
- Maximum: 200 pages
- HTTP connect/read timeout: 4 seconds per operation
- One fetch per page
- Failed URLs recorded

## Railway
Start command:
`gunicorn --workers 1 --threads 4 --timeout 120 app:app`

For production/multiple replicas, replace in-process jobs with Redis/Postgres-backed workers.
