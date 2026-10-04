"""Safe, polite, concurrent website crawler.

What it does that the first version did not:
  * refuses private/internal addresses (SSRF guard), including on every redirect
  * honors robots.txt Disallow rules and Crawl-delay
  * crawls breadth-first so every page gets a real click depth
  * records internal links (and whether each sits in body content or in nav/footer)
  * fetches pages concurrently, with a global request throttle
  * follows redirects by hand so chains are recorded and checked
"""
import gzip
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UA = "KeywordEcosystemBot/0.2 (+site research; honors robots.txt)"
TIMEOUT = (5, 10)            # connect, read (seconds)
MAX_BODY = 2_000_000         # bytes read per page
MAX_REDIRECTS = 5
MAX_SITEMAP_URLS = 5000
MAX_SITEMAP_FILES = 25
WORKERS = 5
TEXT_CAP = 30_000            # characters of body text kept for analysis

TRACKING = {"gclid", "fbclid", "_ga", "msclkid", "mc_cid", "mc_eid", "ref"}
SKIP_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|webp|svg|ico|zip|rar|gz|docx?|xlsx?|pptx?|mp4|mp3|avi|mov|"
    r"css|js|json|xml|txt|woff2?|ttf|eot)$",
    re.I,
)


class CrawlRefused(Exception):
    """The crawl can't or shouldn't run. The message is safe to show to the user."""


class UnsafeURL(CrawlRefused):
    pass


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- URLs

def allow_private():
    """Set ALLOW_PRIVATE_HOSTS=1 only for local testing."""
    return os.environ.get("ALLOW_PRIVATE_HOSTS") == "1"


def assert_public_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise UnsafeURL("Only http and https addresses can be analyzed.")
    host = p.hostname
    if not host:
        raise UnsafeURL("That address has no hostname.")
    if allow_private():
        return
    try:
        port = p.port
    except ValueError:
        raise UnsafeURL("That address has an invalid port.")
    if port not in (None, 80, 443):
        raise UnsafeURL("Only standard web ports (80 and 443) are allowed.")
    try:
        infos = socket.getaddrinfo(host, port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURL(f"Could not find {host}. Check the address.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise UnsafeURL("That address points to a private or internal network, so it can't be analyzed.")


def normalize_url(url, base=None):
    try:
        if base:
            url = urljoin(base, url)
        url, _ = urldefrag(url.strip())
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        host, port = p.hostname.lower(), p.port
    except ValueError:
        return None
    default = 443 if p.scheme == "https" else 80
    netloc = host if port in (None, default) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    qs = sorted(
        (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in TRACKING and not k.lower().startswith("utm_")
    )
    return f"{p.scheme}://{netloc}{path}" + (f"?{urlencode(qs)}" if qs else "")


def site_key(url_or_host):
    """Host without 'www.' (a real prefix strip, unlike lstrip)."""
    s = url_or_host if "://" in url_or_host else f"//{url_or_host}"
    return (urlparse(s).hostname or "").lower().removeprefix("www.")


def same_site(url, key):
    return site_key(url) == key


# ------------------------------------------------------------------------ fetching

class Fetcher:
    """HTTP client: per-thread sessions, global throttle, manual redirects, SSRF checks."""

    def __init__(self, min_interval=0.15):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next = 0.0
        self._local = threading.local()

    def _session(self):
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "en",
            })
            self._local.s = s
        return s

    def _wait(self):
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.min_interval
        if delay:
            time.sleep(delay)

    def fetch(self, url, kind="page"):
        chain, current, net = [], url, 0.0
        out = {"url": url, "final_url": url, "status": 0, "redirects": chain,
               "content_type": "", "body": b"", "elapsed": 0.0, "error": None, "x_robots": ""}
        try:
            for _ in range(MAX_REDIRECTS + 1):
                assert_public_url(current)
                self._wait()
                t0 = time.monotonic()
                r = self._session().get(current, timeout=TIMEOUT, allow_redirects=False, stream=True)
                try:
                    loc = r.headers.get("Location")
                    if r.status_code in (301, 302, 303, 307, 308) and loc:
                        net += time.monotonic() - t0
                        chain.append({"url": current, "status": r.status_code})
                        current = urljoin(current, loc)
                        continue
                    ct = r.headers.get("Content-Type", "").lower()
                    body = b""
                    wants_body = kind != "page" or "html" in ct or not ct
                    if wants_body and r.status_code == 200:
                        for chunk in r.iter_content(65536):
                            body += chunk
                            if len(body) >= MAX_BODY:
                                break
                    net += time.monotonic() - t0
                    out.update(final_url=current, status=r.status_code, content_type=ct,
                               body=body, x_robots=r.headers.get("X-Robots-Tag", ""))
                    return out
                finally:
                    r.close()
            out["error"] = "Too many redirects"
            out["final_url"] = current
        except UnsafeURL as e:
            out["error"] = str(e)
            out["unsafe"] = True
        except requests.exceptions.SSLError:
            out["error"] = "secure connection (HTTPS) failed"
        except requests.exceptions.Timeout:
            out["error"] = "the server took too long to respond"
        except requests.exceptions.ConnectionError:
            out["error"] = "could not connect to the server"
        except requests.RequestException as e:
            out["error"] = type(e).__name__
        finally:
            out["elapsed"] = net
        return out


def load_robots(fetcher, origin):
    res = fetcher.fetch(origin + "/robots.txt", kind="text")
    rp = RobotFileParser()
    sitemaps, found = [], False
    if res["status"] == 200 and res["body"]:
        found = True
        lines = res["body"].decode("utf-8", "replace").splitlines()
        rp.parse(lines)
        sitemaps = [l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("sitemap:")]
    else:
        rp.parse([])
    rp.modified()  # without this, can_fetch() returns False for everything
    delay = None
    try:
        delay = rp.crawl_delay(UA)
    except Exception:
        pass
    return rp, sitemaps, delay, found


def read_sitemaps(fetcher, seeds, cancelled):
    urls, files, seen, queue = [], [], set(), list(seeds)
    while queue and len(seen) < MAX_SITEMAP_FILES and len(urls) < MAX_SITEMAP_URLS:
        if cancelled():
            raise Cancelled()
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        res = fetcher.fetch(sm, kind="sitemap")
        if res["status"] != 200 or not res["body"]:
            continue
        body = res["body"]
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(5_000_000)
            except OSError:
                continue
        text = body[:5_000_000].decode("utf-8", "replace")
        locs = [html.unescape(x.strip()) for x in
                re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", text, re.S | re.I)]
        files.append(sm)
        if re.search(r"<sitemapindex", text, re.I):
            queue.extend(locs)
        else:
            urls.extend(locs)
    return files, urls[:MAX_SITEMAP_URLS]


# ------------------------------------------------------------------------- parsing

def _schema_types(soup):
    types = set()

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if isinstance(t, str):
                types.add(t)
            elif isinstance(t, list):
                types.update(x for x in t if isinstance(x, str))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(s.string or ""))
        except (ValueError, TypeError):
            pass
    return sorted(types)[:10]


def parse_page(res, requested, base_key):
    final = normalize_url(res["final_url"]) or requested
    soup = BeautifulSoup(res["body"], "lxml")

    def meta(name=None, prop=None):
        attrs = {"name": re.compile(f"^{name}$", re.I)} if name else {"property": re.compile(f"^{prop}$", re.I)}
        m = soup.find("meta", attrs=attrs)
        return (m.get("content") or "").strip() if m else ""

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    canon_tag = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    canonical = (canon_tag.get("href") or "").strip() if canon_tag else ""
    robots_meta = meta(name="robots")
    h1 = [x.get_text(" ", strip=True) for x in soup.find_all("h1")]
    h2 = [x.get_text(" ", strip=True) for x in soup.find_all("h2")]
    h3_count = len(soup.find_all("h3"))
    imgs = soup.find_all("img")
    images_no_alt = sum(1 for i in imgs if i.get("alt") is None)
    schema = _schema_types(soup)

    internal, external = [], 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "sms:", "data:")):
            continue
        target = normalize_url(href, final)
        if not target:
            continue
        if not same_site(target, base_key):
            external += 1
            continue
        if SKIP_EXT.search(urlparse(target).path):
            continue
        in_body = a.find_parent(["nav", "header", "footer", "aside"]) is None
        rel = a.get("rel") or []
        internal.append((target, in_body, "nofollow" in [r.lower() for r in rel]))

    for t in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    drop = ["nav", "footer", "aside"] + (["header"] if main is soup.body else [])
    for t in main.find_all(drop):
        t.decompose()
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
    words = re.findall(r"\b\w[\w'’-]*\b", text)
    norm_text = text.lower()[:6000]
    return {
        "url": final, "requested": requested,
        "path": urlparse(final).path or "/",
        "status": res["status"],
        "title": title, "meta": meta(name="description"),
        "h1": h1[:5], "h2": h2[:20], "h3_count": h3_count,
        "canonical": canonical, "robots_meta": robots_meta,
        "noindex": "noindex" in robots_meta.lower() or "noindex" in res.get("x_robots", "").lower(),
        "lang": (soup.html.get("lang") if soup.html else "") or "",
        "og_type": meta(prop="og:type"), "schema": schema,
        "word_count": len(words), "text": text[:TEXT_CAP],
        "text_hash": hashlib.sha1(norm_text.encode()).hexdigest() if len(words) >= 50 else "",
        "images": len(imgs), "images_no_alt": images_no_alt,
        "links_internal": internal, "external_count": external,
        "elapsed_ms": int(res["elapsed"] * 1000), "redirects": len(res["redirects"]),
        "depth": None, "in_sitemap": False,
    }


# --------------------------------------------------------------------------- crawl

def _process(fetcher, url, robots, base_key):
    if not robots.can_fetch(UA, url):
        return {"url": url, "blocked": True}
    res = fetcher.fetch(url)
    page = None
    if res["status"] == 200 and res["body"] and ("html" in res["content_type"] or not res["content_type"]):
        page = parse_page(res, url, base_key)
    res = {k: v for k, v in res.items() if k != "body"}
    return {"url": url, "res": res, "page": page}


def crawl(start_url, max_pages=75, on_progress=None, cancelled=None):
    cancelled = cancelled or (lambda: False)
    on_progress = on_progress or (lambda n, total, msg: None)
    started = time.monotonic()

    root = normalize_url(start_url if "://" in start_url else "https://" + start_url)
    if not root:
        raise CrawlRefused("That doesn't look like a valid web address.")
    assert_public_url(root)
    origin = "{0.scheme}://{0.netloc}".format(urlparse(root))
    base_key = site_key(root)

    fetcher = Fetcher()
    on_progress(0, max_pages, "Reading robots.txt and sitemaps")
    robots, robots_sitemaps, delay, robots_found = load_robots(fetcher, origin)
    if delay:
        fetcher.min_interval = max(fetcher.min_interval, min(delay, 5.0))
    if not robots.can_fetch(UA, root):
        raise CrawlRefused("This site's robots.txt does not allow crawling this address.")

    seeds = list(dict.fromkeys(robots_sitemaps + [origin + p for p in
                 ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")]))
    sm_files, sm_raw = read_sitemaps(fetcher, seeds, cancelled)

    pages, failed, blocked = {}, [], []
    redirect_map = {}
    seen, depth_of = {root}, {root: 0}
    frontier, sm_queue = [root], []
    sm_loaded = False
    attempts, non_html, max_depth = 0, 0, 0
    sitemap_set = set()

    def merge(r):
        nonlocal non_html, base_key
        u = r["url"]
        if r.get("blocked"):
            blocked.append(u)
            return []
        res, page = r["res"], r["page"]
        final = normalize_url(res["final_url"]) or u
        if final != u:
            redirect_map[u] = final
        if res["error"]:
            failed.append({"url": u, "status": 0, "reason": res["error"]})
            return []
        if res["status"] != 200:
            failed.append({"url": u, "status": res["status"], "reason": f"HTTP {res['status']}"})
            return []
        if page is None:
            non_html += 1
            return []
        if u == root and not pages and not same_site(final, base_key):
            base_key = site_key(final)  # homepage redirected to a different domain
        elif not same_site(final, base_key):
            failed.append({"url": u, "status": 200, "reason": "Redirects to another website"})
            return []
        if final in pages:
            return []
        page["depth"] = depth_of.get(u)
        pages[final] = page
        new = []
        d = page["depth"]
        for target, _in_body, _nf in page["links_internal"]:
            if target in seen or target == final:
                continue
            seen.add(target)
            depth_of[target] = None if d is None else d + 1
            new.append(target)
        return new

    while (frontier or sm_queue or not sm_loaded) and len(pages) < max_pages and attempts < max_pages * 3:
        if not frontier:
            if not sm_loaded:
                sm_loaded = True
                sitemap_set = {n for n in (normalize_url(x) for x in sm_raw) if n and same_site(n, base_key)}
                sm_queue = [u for u in sitemap_set if u not in seen]
                seen.update(sm_queue)
                for u in sm_queue:
                    depth_of[u] = None
            if sm_queue:
                frontier, sm_queue = sm_queue, []
            else:
                break
        budget = max_pages - len(pages)
        batch, rest = frontier[:budget], frontier[budget:]
        attempts += len(batch)
        new_links = []
        with ThreadPoolExecutor(WORKERS) as ex:
            futures = [ex.submit(_process, fetcher, u, robots, base_key) for u in batch]
            for fut in as_completed(futures):
                if cancelled():
                    for f in futures:
                        f.cancel()
                    raise Cancelled()
                new_links.extend(merge(fut.result()))
                if pages:
                    max_depth = max(max_depth, max((p["depth"] or 0) for p in pages.values()))
                on_progress(len(pages), max_pages,
                            f"Crawled {len(pages)} of up to {max_pages} pages (click depth {max_depth})")
        frontier = rest + new_links

    if not sm_loaded:
        sitemap_set = {n for n in (normalize_url(x) for x in sm_raw) if n and same_site(n, base_key)}
    for p in pages.values():
        p["in_sitemap"] = p["url"] in sitemap_set or p["requested"] in sitemap_set

    if not pages:
        reason = failed[0]["reason"] if failed else "no HTML page was returned"
        raise CrawlRefused(f"Couldn't read the homepage ({reason}).")

    # who links to each broken URL (up to 3 sources)
    broken = {f["url"] for f in failed}
    sources = {}
    for p in pages.values():
        for target, _b, _n in p["links_internal"]:
            if target in broken and len(sources.setdefault(target, [])) < 3 and p["url"] not in sources[target]:
                sources[target].append(p["url"])
    for f in failed:
        f["linked_from"] = sources.get(f["url"], [])

    return {
        "root": next(iter(pages)), "base_key": base_key,
        "pages": list(pages.values()), "failed": failed, "blocked": blocked,
        "redirect_map": redirect_map,
        "sitemap": {"files": sm_files, "urls": sorted(sitemap_set)},
        "robots": {"found": robots_found, "crawl_delay": delay, "sitemaps": robots_sitemaps},
        "truncated": bool(frontier or sm_queue),
        "non_html_skipped": non_html, "urls_discovered": len(seen),
        "duration_s": round(time.monotonic() - started, 1), "max_pages": max_pages,
    }
