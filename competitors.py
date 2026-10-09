"""Compare the user's site with competitor sites, using the same analysis on both."""
from urllib.parse import urlparse

from analysis import tokens

SKIP_TYPES = {"Company / Utility", "Archive / Listing", "Category / Listing", "Home"}


def _tset(p):
    return set(tokens(p["title"] + " " + " ".join(p["h1"])))


def summarize(you, comp_data, comp_res):
    """you: your analysis result. comp_data: crawl output. comp_res: analysis.analyze(comp_data, keywords)."""
    pages = comp_data["pages"]
    cp = {p["url"]: p for p in comp_res["pages"]}
    yours = {p["url"]: p for p in you["pages"]}
    rows = []
    for yk, ck in zip(you["keywords"], comp_res["keywords"]):
        best = ck["ranking"][0] if ck["ranking"] else None
        page = cp.get(best["url"]) if best else None
        mine = yk["closest"]
        mine_page = yours.get(mine["url"])
        if not best:
            continue
        diff = best["score"] - yk["score"]
        rows.append({"keyword": yk["keyword"], "your_score": yk["score"], "your_path": mine["path"],
                     "your_words": mine_page["word_count"] if mine_page else 0,
                     "their_score": best["score"], "their_url": best["url"], "their_path": best["path"],
                     "their_title": best["title"], "their_words": page["word_count"] if page else 0,
                     "their_inbound": page["inbound"] if page else 0,
                     "verdict": "Their page is stronger" if diff >= 15 else "Your page is stronger" if diff <= -15 else "Similar"})
    mine_sets = [_tset(p) for p in you["pages"]]
    lacking = []
    for p in pages:
        if p["page_type"] in SKIP_TYPES or p["word_count"] < 200:
            continue
        ts = _tset(p)
        if len(ts) < 2:
            continue
        best = max((len(ts & m) / len(ts | m) for m in mine_sets if m), default=0)
        if best < 0.34:
            lacking.append({"title": p["title"], "url": p["url"], "words": p["word_count"]})
    lacking.sort(key=lambda x: -x["words"])
    types = {}
    for p in pages:
        types[p["page_type"]] = types.get(p["page_type"], 0) + 1
    return {
        "url": comp_data["root"], "domain": comp_data["base_key"], "pages": len(pages),
        "crawl_limited": comp_data["truncated"],
        "avg_words": round(sum(p["word_count"] for p in pages) / len(pages)),
        "page_types": types,
        "blog_posts": types.get("Blog / Article", 0),
        "has_faq_schema": sum(1 for p in pages if "FAQPage" in p["schema"]),
        "has_local_schema": sum(1 for p in pages if {"LocalBusiness"} & set(p["schema"])),
        "keywords": rows, "topics_you_lack": lacking[:12],
    }
