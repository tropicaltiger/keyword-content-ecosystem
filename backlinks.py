"""Backlink gap from exported CSVs (no data provider needed).

Crawling cannot discover who links to a site; that needs a backlink index (Ahrefs, Semrush, Moz...).
So the user pastes or uploads exports, and this module finds sites that link to competitors but not to you.
"""
import csv
import io
import re
from collections import defaultdict
from urllib.parse import urlparse

MULTI = {"co.in", "org.in", "net.in", "gov.in", "ac.in", "edu.in", "co.uk", "org.uk", "ac.uk", "gov.uk",
         "com.au", "org.au", "net.au", "edu.au", "gov.au", "co.nz", "co.za", "com.sg", "com.my", "com.br",
         "co.jp", "co.ae", "com.ae", "net.ae", "org.ae"}
HOSTED = {"blogspot.com", "wordpress.com", "wixsite.com", "medium.com", "tumblr.com", "weebly.com", "github.io"}
SOCIAL = {"facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "pinterest.com",
          "reddit.com", "quora.com", "medium.com", "tumblr.com", "t.me"}
DIR_WORDS = ("directory", "yellow", "justdial", "sulekha", "yelp", "listing", "indiamart", "tradeindia", "localsearch",
             "cylex", "bbb.org", "manta", "foursquare", "yell.com", "hotfrog", "clutch", "practo", "lybrate", "wedmegood")
NEWS_WORDS = ("news", "times", "herald", "post", "today", "express", "hindu", "tribune", "gazette", "magazine", "press")
HEADER_PREF = ("referring page url", "referring url", "source url", "from url", "referring domain", "source domain",
               "referring page", "domain", "source", "from")


def registrable(host):
    host = host.lower().strip(".").removeprefix("www.")
    parts = host.split(".")
    if len(parts) < 2:
        return host
    tail2 = ".".join(parts[-2:])
    if tail2 in MULTI and len(parts) >= 3:
        return ".".join(parts[-3:])
    if tail2 in HOSTED and len(parts) > 2:
        return ".".join(parts[-3:])
    return tail2


def domain_of(cell):
    v = (cell or "").strip().strip('"').strip()
    if not v or " " in v:
        return None
    if "://" in v:
        host = urlparse(v).hostname
    elif re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", v):
        host = urlparse("//" + v).hostname
    else:
        return None
    return registrable(host) if host and "." in host else None


def parse_domains(text):
    text = (text or "")[:1_500_000]
    if not text.strip():
        return set()
    first = text.splitlines()[0]
    delim = max((",", ";", "\t"), key=first.count)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r]
    width = max(len(r) for r in rows)
    sample = rows[:300]
    best, best_rank = 0, 99
    for i in range(width):
        ok = sum(1 for r in sample if i < len(r) and domain_of(r[i]))
        if ok < max(1, len(sample) * 0.5):
            continue
        head = (rows[0][i] if i < len(rows[0]) else "").lower()
        rank = next((n for n, h in enumerate(HEADER_PREF) if h in head), 50)
        if rank < best_rank:
            best, best_rank = i, rank
    return {d for r in rows if best < len(r) for d in [domain_of(r[best])] if d}


def classify(d):
    if d in SOCIAL:
        return "Social or community profile", "Quick: create a profile"
    if d.endswith((".gov", ".gov.in", ".edu", ".ac.in", ".edu.in", ".ac.uk", ".gov.uk", ".edu.au", ".gov.au")):
        return "Government or education", "Hard: has to be earned"
    if any(w in d for w in DIR_WORDS):
        return "Directory or listing", "Quick: submit a listing"
    if any(w in d for w in NEWS_WORDS):
        return "News or media", "Medium: pitch a story"
    if any(w in d for w in ("blog", "wordpress", "blogspot", "wixsite")):
        return "Blog", "Medium: guest post or useful comment"
    return "Other website", "Medium: outreach"


def gap(yours, competitors, own_domain=""):
    """competitors: list of (name, set_of_domains). Returns sites linking to a competitor but not you."""
    comp_own = set()
    counts = defaultdict(set)
    for name, doms in competitors:
        for d in doms:
            counts[d].add(name)
    rows = []
    for d, names in counts.items():
        if d in yours or d == own_domain or d in comp_own:
            continue
        kind, ease = classify(d)
        rows.append({"domain": d, "count": len(names), "linked_to": sorted(names), "kind": kind, "ease": ease})
    order = {"Quick": 0, "Medium": 1, "Hard": 2}
    rows.sort(key=lambda r: (-r["count"], order.get(r["ease"].split(":")[0], 1), r["domain"]))
    return {"prospects": rows[:150], "total": len(rows), "yours": len(yours),
            "competitor_domains": {n: len(d) for n, d in competitors}}
