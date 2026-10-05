"""Keyword Content Ecosystem: Flask API and job runner.

POST   /api/analyze      start a crawl, returns a job id
GET    /api/plan/<id>    free ecosystem map and platform playbook for a finished analysis
POST   /api/content      start AI writing for a finished analysis (needs ANTHROPIC_API_KEY)
GET    /api/jobs/<id>    progress, and the result when finished
DELETE /api/jobs/<id>    cancel a running job
GET    /api/config       tells the UI whether an access key is needed
GET    /api/health       liveness check

Environment variables
  APP_ACCESS_KEY        if set, API calls must send it in the X-Access-Key header
  MAX_CONCURRENT_JOBS   crawls running at once (default 2)
  RATE_LIMIT_PER_HOUR   crawls one IP may start per hour (default 10)
  ANTHROPIC_API_KEY     turns on AI writing (GBP posts, FAQs, platform content)
  ANTHROPIC_MODEL       model used for writing (default claude-sonnet-5-5)
  CONTENT_LIMIT_PER_HOUR  writing runs one IP may start per hour (default 6)
  ALLOW_PRIVATE_HOSTS   set to 1 ONLY for local testing (disables the SSRF guard)
"""
import hmac
import os
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request

import analysis
import content
import crawler

app = Flask(__name__)

ACCESS_KEY = os.environ.get("APP_ACCESS_KEY", "")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_HOUR", "10"))
CONTENT_LIMIT = int(os.environ.get("CONTENT_LIMIT_PER_HOUR", "6"))
MAX_JOBS_KEPT = 40
JOB_TTL = 2 * 3600

EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get("MAX_CONCURRENT_JOBS", "2")))
JOBS = OrderedDict()
CANCEL = {}
HITS = defaultdict(deque)
LOCK = threading.Lock()


# ------------------------------------------------------------------------- helpers

def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() or request.remote_addr or "unknown"


def update(job_id, **fields):
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def purge_jobs():
    """Drop expired jobs and keep memory bounded. Call with LOCK held."""
    now = time.time()
    for jid in [j for j, v in JOBS.items() if now - v["created"] > JOB_TTL and v["status"] not in ("queued", "running")]:
        JOBS.pop(jid, None)
        CANCEL.pop(jid, None)
    while len(JOBS) > MAX_JOBS_KEPT:
        oldest = next((j for j, v in JOBS.items() if v["status"] not in ("queued", "running")), None)
        if not oldest:
            break
        JOBS.pop(oldest, None)
        CANCEL.pop(oldest, None)


def rate_limited(ip, limit=None, bucket=""):
    now = time.time()
    q = HITS[bucket + ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= (limit or RATE_LIMIT):
        return True
    q.append(now)
    return False


@app.before_request
def require_key():
    if not ACCESS_KEY or not request.path.startswith("/api/") or request.path in ("/api/health", "/api/config"):
        return None
    given = request.headers.get("X-Access-Key", "")
    if not hmac.compare_digest(given.encode(), ACCESS_KEY.encode()):
        return jsonify(error="An access key is required."), 401
    return None


# --------------------------------------------------------------------------- jobs

def run_job(job_id, url, keywords, max_pages):
    cancel = CANCEL[job_id]
    try:
        update(job_id, status="running", progress=2, message="Starting")

        def on_progress(done, total, msg):
            update(job_id, progress=min(88, 3 + int(85 * done / max(total, 1))), message=msg)

        data = crawler.crawl(url, max_pages, on_progress=on_progress, cancelled=cancel.is_set)
        update(job_id, progress=92, message="Matching keywords to pages")
        result = analysis.analyze(data, keywords)
        update(job_id, status="complete", progress=100, message="Done", result=result)
    except crawler.Cancelled:
        update(job_id, status="cancelled", progress=100, message="Cancelled")
    except crawler.CrawlRefused as e:
        update(job_id, status="failed", progress=100, message=str(e))
    except Exception:
        app.logger.exception("Job %s failed", job_id)
        update(job_id, status="failed", progress=100,
               message="Something went wrong while analyzing this site. Try again, or try fewer pages.")


# -------------------------------------------------------------------------- routes

@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/config")
def api_config():
    return jsonify(auth_required=bool(ACCESS_KEY), ai_enabled=content.ai_enabled())


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    keywords = []
    for k in data.get("keywords", []):
        k = " ".join(str(k).split())[:80]
        if k and k.lower() not in [x.lower() for x in keywords]:
            keywords.append(k)
    keywords = keywords[:5]
    try:
        max_pages = min(max(int(data.get("max_pages", 75)), 10), 300)
    except (TypeError, ValueError):
        max_pages = 75
    if not url or not keywords:
        return jsonify(error="Enter a website address and at least one keyword."), 400

    # validate the address up front so mistakes fail instantly instead of inside the job
    check = crawler.normalize_url(url if "://" in url else "https://" + url)
    try:
        if not check:
            raise crawler.CrawlRefused("That doesn't look like a valid web address.")
        crawler.assert_public_url(check)
    except crawler.CrawlRefused as e:
        return jsonify(error=str(e)), 400

    with LOCK:
        if rate_limited(client_ip()):
            return jsonify(error=f"Limit reached: {RATE_LIMIT} analyses per hour. Try again later."), 429
        purge_jobs()
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Waiting for a free worker",
                        "created": time.time()}
        CANCEL[job_id] = threading.Event()
    EXECUTOR.submit(run_job, job_id, url, keywords, max_pages)
    return jsonify(job_id=job_id, status="queued"), 202


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error="Job not found. It may have expired."), 404
        return jsonify({k: v for k, v in job.items() if k != "created"})


@app.delete("/api/jobs/<job_id>")
def api_cancel(job_id):
    ev = CANCEL.get(job_id)
    if not ev:
        return jsonify(error="Job not found."), 404
    ev.set()
    return jsonify(ok=True)


def run_content_job(job_id, analysis_result, form, channels):
    result = {"channels": {}, "errors": {}}
    update(job_id, status="running", progress=5, message="Writing", result=result)

    def on_result(ch, data, err):
        with LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            if err:
                job["result"]["errors"][ch] = err
            else:
                job["result"]["channels"][ch] = data
            done = len(job["result"]["channels"]) + len(job["result"]["errors"])
            job["progress"] = 5 + int(95 * done / len(channels))
            job["message"] = f"Finished {done} of {len(channels)}"

    try:
        content.generate(analysis_result, form, channels, on_result)
        update(job_id, status="complete", progress=100, message="Done")
    except Exception:
        app.logger.exception("Content job %s failed", job_id)
        update(job_id, status="failed", progress=100, message="Something went wrong while writing.")


@app.get("/api/plan/<job_id>")
def api_plan(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        res = job.get("result") if job and job["status"] == "complete" and "keywords" in (job.get("result") or {}) else None
    if not res:
        return jsonify(error="Run an analysis first."), 404
    btype = "online" if request.args.get("type") == "online" else "local"
    return jsonify(ecosystem=content.ecosystem_map(res),
                   playbook=content.playbook(btype, request.args.get("country", "")[:30]))


@app.post("/api/content")
def api_content():
    d = request.get_json(silent=True) or {}
    with LOCK:
        job = JOBS.get(str(d.get("job_id", "")))
        res = job.get("result") if job and job["status"] == "complete" else None
    if not res or "keywords" not in res:
        return jsonify(error="Run an analysis first, then write content from its results."), 400
    if not content.ai_enabled():
        return jsonify(error="AI writing is not switched on. Add ANTHROPIC_API_KEY in your server settings."), 400
    channels = [c for c in d.get("channels", []) if c in content.CHANNELS][:7]
    if not channels:
        return jsonify(error="Pick at least one channel to write."), 400
    form = {
        "business_name": " ".join(str(d.get("business_name", "")).split())[:80],
        "city": " ".join(str(d.get("city", "")).split())[:60],
        "country": " ".join(str(d.get("country", "")).split())[:40],
        "tone": d.get("tone") if d.get("tone") in content.TONES else "friendly",
        "language": " ".join(str(d.get("language", "English")).split())[:40] or "English",
        "extra_facts": str(d.get("extra_facts", "")).strip()[:1500],
    }
    with LOCK:
        if rate_limited(client_ip(), CONTENT_LIMIT, "content:"):
            return jsonify(error=f"Limit reached: {CONTENT_LIMIT} writing runs per hour. Try again later."), 429
        purge_jobs()
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Waiting for a free worker",
                        "created": time.time()}
        CANCEL[job_id] = threading.Event()
    EXECUTOR.submit(run_content_job, job_id, res, form, channels)
    return jsonify(job_id=job_id, status="queued"), 202


@app.get("/api/health")
def api_health():
    with LOCK:
        active = sum(1 for j in JOBS.values() if j["status"] in ("queued", "running"))
    return jsonify(ok=True, service="keyword-content-ecosystem", active_jobs=active)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
