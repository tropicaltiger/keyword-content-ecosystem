"""Turns raw crawl data into keyword decisions, issues and site structure."""
import re
import time
from collections import Counter, defaultdict
from urllib.parse import unquote, urljoin, urlparse

from crawler import normalize_url, site_key

# ------------------------------------------------------------------- text helpers

STOP = set("""a an the and or of for to in on at by with from your our is are be this that it as
you we how what why when where which who can do does""".split())


def stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text, keep_stop=False):
    words = re.findall(r"[a-z0-9\u00c0-\uffff]+", (text or "").lower())
    return [stem(w) for w in words if len(w) > 1 and (keep_stop or w not in STOP)]


def phrase_count(seq, phrase):
    n = len(phrase)
    if n == 0 or len(seq) < n:
        return 0
    if n == 1:
        return seq.count(phrase[0])
    return sum(1 for i in range(len(seq) - n + 1) if seq[i:i + n] == phrase)


def build_index(p):
    path_text = re.sub(r"[-_/.]+", " ", unquote(p["path"]))
    idx = {
        "title": tokens(p["title"]), "h1": tokens(" ".join(p["h1"])),
        "h2": tokens(" ".join(p["h2"])), "meta": tokens(p["meta"]),
        "url": tokens(path_text), "body": tokens(p["text"]),
    }
    return {"seq": idx, "sets": {k: set(v) for k, v in idx.items()},
            "body_counts": Counter(idx["body"])}


FIELD_W = {"title": 3.0, "h1": 3.0, "url": 2.5, "meta": 1.5, "h2": 1.5, "body": 1.0}
PHRASE_W = {"title": 1.0, "h1": 1.0, "url": 0.8, "h2": 0.7, "meta": 0.6}


def score_page(kt, idx):
    """0-100 relevance of one page to one keyword, plus where the keyword appears."""
    cov_total = 0.0
    found = {}
    for f, w in FIELD_W.items():
        present = sum(1 for t in kt if t in idx["sets"][f]) / len(kt)
        cov_total += w * present
        found[f] = present == 1.0
    cov = cov_total / sum(FIELD_W.values())

    phrase = 0.0
    for f, w in PHRASE_W.items():
        if phrase_count(idx["seq"][f], kt):
            phrase = max(phrase, w)
    body_hits = phrase_count(idx["seq"]["body"], kt)
    phrase = max(phrase, min(1.0, body_hits / 3) * 0.5)
    found["body_count"] = body_hits

    tf = sum(idx["body_counts"][t] / (idx["body_counts"][t] + 3) for t in kt) / len(kt)
    return round(100 * (0.45 * cov + 0.35 * phrase + 0.20 * tf)), found


# ----------------------------------------------------------------- classification

BLOG = {"blog", "news", "article", "articles", "insights", "post", "posts", "guide", "guides",
        "learn", "resources", "stories", "press"}
UTILITY = {"about", "contact", "privacy", "terms", "cookie", "cookies", "careers", "career", "login",
           "signin", "cart", "checkout", "account", "sitemap", "faq", "policy", "disclaimer"}
SERVICE = {"service", "services", "solution", "solutions", "product", "products", "training", "course",
           "courses", "pricing", "shop", "offering", "consulting", "packages"}


def classify(p, n_links):
    path = unquote(p["path"]).lower()
    if path == "/":
        return "Home"
    toks = set(re.split(r"[^a-z0-9]+", path))
    schema = set(p["schema"])
    if toks & UTILITY:
        return "Company / Utility"
    if toks & BLOG or schema & {"Article", "BlogPosting", "NewsArticle"} or p["og_type"] == "article":
        return "Blog / Article"
    if "case-stud" in path or "portfolio" in toks:
        return "Case Study"
    if toks & SERVICE or schema & {"Product", "Service", "Course", "Offer"}:
        return "Service / Product"
    if n_links >= 40 and p["word_count"] < 400:
        return "Category / Listing"
    return "Other"


INFO_W = {"how", "what", "why", "guide", "tutorial", "tips", "learn", "meaning", "definition", "examples",
          "ideas", "checklist", "difference", "explained"}
COMM_W = {"best", "top", "review", "reviews", "compare", "comparison", "alternative", "alternatives", "vs"}
TRANS_W = {"buy", "price", "pricing", "cost", "cheap", "hire", "quote", "book", "order", "shop", "service",
           "services", "company", "companies", "agency", "consultant", "consultants", "near", "provider",
           "providers", "supplier", "suppliers", "course", "courses", "training", "jobs", "job"}
EXPECTED = {
    "info": {"Blog / Article"},
    "comm": {"Blog / Article", "Service / Product"},
    "trans": {"Service / Product", "Category / Listing", "Home"},
}
INTENT_LABEL = {"info": "Informational", "comm": "Commercial research",
                "trans": "Transactional", "mixed": "Unclear"}


def intent_of(keyword):
    words = set(re.findall(r"[a-z0-9]+", keyword.lower()))
    hits = {"info": len(words & INFO_W), "comm": len(words & COMM_W), "trans": len(words & TRANS_W)}
    best = max(hits, key=hits.get)
    return best if hits[best] else "mixed"


# --------------------------------------------------------------------------- main

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
LEVEL = {"high": "bad", "medium": "warn", "low": "note"}


def analyze(data, keywords):
    pages = data["pages"]
    redirect_map = data["redirect_map"]
    base_key = data["base_key"]
    by_url = {p["url"]: p for p in pages}

    def resolve(u):
        for _ in range(5):
            if u in redirect_map:
                u = redirect_map[u]
            else:
                break
        return u

    # ---- link graph
    in_all, in_ctx = defaultdict(set), defaultdict(set)
    for p in pages:
        out = set()
        for target, in_body, _nofollow in p["links_internal"]:
            t = resolve(target)
            if t in by_url and t != p["url"]:
                out.add(t)
                in_all[t].add(p["url"])
                if in_body:
                    in_ctx[t].add(p["url"])
        p["_out"] = out
    for p in pages:
        p["inbound"] = len(in_all[p["url"]])
        p["inbound_body"] = len(in_ctx[p["url"]])
        p["outbound"] = len(p["_out"])
        p["page_type"] = classify(p, len(p["links_internal"]))
        p["_idx"] = build_index(p)
        p["flags"] = []

    home = by_url.get(data["root"]) or pages[0]
    brand = ""
    for sep in ("|", " – ", " — ", " - "):
        if sep in home["title"]:
            brand = home["title"].split(sep)[-1].strip()
            break
    if len(brand) > 30:
        brand = ""

    # ---- issues
    issues = {}

    def issue(key, severity, category, title, fix, url, detail=""):
        it = issues.setdefault(key, {"type": key, "severity": severity, "category": category,
                                     "title": title, "fix": fix, "items": []})
        it["items"].append({"url": url, "detail": detail})

    def flag(p, label, severity):
        p["flags"].append({"label": label, "level": LEVEL[severity]})

    dup_title, dup_meta, dup_text = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in pages:
        u = p["url"]
        is_utility = p["page_type"] in ("Company / Utility", "Category / Listing")
        if not p["title"]:
            issue("no_title", "high", "On-page", "Missing title tag",
                  "Add a unique, descriptive title that includes the page's main keyword.", u)
            flag(p, "NO TITLE", "high")
        else:
            dup_title[p["title"].strip().lower()].append(u)
            if len(p["title"]) > 60:
                issue("long_title", "low", "On-page", "Title may be cut off in search results (over 60 characters)",
                      "Shorten the title and put the keyword near the start.", u, f"{len(p['title'])} characters")
        if not p["h1"]:
            issue("no_h1", "medium", "On-page", "Missing H1 heading",
                  "Add one H1 that states what the page is about.", u)
            flag(p, "NO H1", "medium")
        elif len(p["h1"]) > 1:
            issue("multi_h1", "low", "On-page", "More than one H1 heading",
                  "Keep a single H1 and use H2s for sections.", u, f"{len(p['h1'])} H1s")
            flag(p, "MULTIPLE H1", "low")
        if not p["meta"]:
            issue("no_meta", "medium", "On-page", "Missing meta description",
                  "Write a 120-160 character description that earns the click.", u)
            flag(p, "NO META", "medium")
        else:
            dup_meta[p["meta"].strip().lower()].append(u)
            if len(p["meta"]) > 160:
                issue("long_meta", "low", "On-page", "Meta description may be truncated (over 160 characters)",
                      "Trim it so the key message shows in full.", u, f"{len(p['meta'])} characters")
        if p["word_count"] < 300 and not is_utility:
            issue("thin", "medium", "Content", "Thin content (under 300 words)",
                  "Expand with sections that answer what searchers want, or merge into a stronger page.",
                  u, f"{p['word_count']} words")
            flag(p, "THIN", "medium")
        if p["text_hash"]:
            dup_text[p["text_hash"]].append(u)
        if p["noindex"]:
            issue("noindex", "medium", "Indexing", "Page is set to noindex",
                  "Remove noindex if this page should appear in search results.", u)
            flag(p, "NOINDEX", "medium")
        if p["canonical"]:
            canon = normalize_url(urljoin(u, p["canonical"]))
            if canon and canon != u:
                off = site_key(canon) != base_key
                issue("canonical_elsewhere", "high" if off else "medium", "Indexing",
                      "Canonical tag points to a different URL",
                      "Point the canonical to the page itself, unless this is intentionally a duplicate.",
                      u, f"canonical: {canon}")
                flag(p, "CANONICAL ELSEWHERE", "high" if off else "medium")
        else:
            issue("no_canonical", "low", "Indexing", "No canonical tag",
                  "Add a self-referencing canonical to avoid duplicate-URL issues.", u)
        if p["images_no_alt"]:
            issue("img_alt", "low", "On-page", "Images without alt attributes",
                  "Add short descriptive alt text to meaningful images.", u,
                  f"{p['images_no_alt']} of {p['images']} images")
        if p["elapsed_ms"] > 2500:
            issue("slow", "low", "Technical", "Slow server response (over 2.5 s)",
                  "Check hosting, caching and heavy server-side work.", u, f"{p['elapsed_ms']} ms")
        if p["redirects"] >= 2:
            issue("redirect_chain", "medium", "Technical", "Redirect chain (two or more hops)",
                  "Redirect straight to the final URL.", u, f"{p['redirects']} hops")
        if p["depth"] is not None and p["depth"] >= 4:
            issue("deep", "low", "Structure", "Page is four or more clicks from the homepage",
                  "Link it from a hub page or navigation so it is easier to reach.", u, f"depth {p['depth']}")
            flag(p, "DEEP", "low")
        if p["depth"] is None and not in_all[u]:
            sev = "low" if data["truncated"] else "medium"
            issue("orphan", sev, "Structure",
                  "Possible orphan page (in sitemap, not linked from crawled pages)" if data["truncated"]
                  else "Orphan page (in sitemap, but no page links to it)",
                  "Add internal links from related pages, or remove it from the sitemap.", u)
            flag(p, "ORPHAN", sev)

    for label, groups, key, title, fix in (
        ("DUP TITLE", dup_title, "dup_title", "Duplicate title tags", "Give each page its own title."),
        ("DUP META", dup_meta, "dup_meta", "Duplicate meta descriptions", "Write a unique description per page."),
        ("DUP CONTENT", dup_text, "dup_content", "Near-identical page content",
         "Merge the pages, differentiate them, or canonicalize to one."),
    ):
        for urls in groups.values():
            if len(urls) > 1:
                for u in urls:
                    issue(key, "medium", "Content", title, fix, u, f"shared with {len(urls) - 1} other page(s)")
                    flag(by_url[u], label, "medium")

    # broken URLs
    for f in data["failed"]:
        src = ", ".join(urlparse(s).path or "/" for s in f["linked_from"]) or "found in sitemap"
        if f["status"] in (404, 410):
            issue("broken_4xx", "high", "Technical", "Broken links (404/410)",
                  "Fix or remove the link, or redirect the URL to the closest live page.",
                  f["url"], f"linked from: {src}")
        elif f["status"] >= 400:
            issue("http_error", "high", "Technical", "Pages returning errors (4xx/5xx)",
                  "Check why the server is refusing these URLs.", f["url"], f"{f['reason']}; linked from: {src}")
        else:
            issue("fetch_failed", "medium", "Technical", "URLs that could not be fetched",
                  "Check these URLs load for visitors and for crawlers.", f["url"], f"{f['reason']}; linked from: {src}")

    # links to redirecting URLs
    for p in pages:
        for target, _b, _n in p["links_internal"]:
            if target in redirect_map:
                issue("links_to_redirect", "low", "Technical", "Internal links that go through a redirect",
                      "Update the link to point at the final URL.", p["url"],
                      f"{urlparse(target).path or '/'} → {urlparse(redirect_map[target]).path or '/'}")

    # sitemap hygiene
    sm_urls = set(data["sitemap"]["urls"])
    failed_urls = {f["url"] for f in data["failed"]}
    for u in sorted(sm_urls & failed_urls):
        issue("sitemap_broken", "high", "Sitemap", "Sitemap lists URLs that fail to load",
              "Remove broken URLs from the sitemap.", u)
    for u in sorted(sm_urls & set(redirect_map)):
        issue("sitemap_redirect", "medium", "Sitemap", "Sitemap lists URLs that redirect",
              "List the final URL instead.", u, f"→ {urlparse(redirect_map[u]).path or '/'}")
    for p in pages:
        if p["noindex"] and p["in_sitemap"]:
            issue("sitemap_noindex", "high", "Sitemap", "Sitemap lists noindex pages",
                  "Remove them from the sitemap or remove the noindex.", p["url"])
    if sm_urls:
        if not data["truncated"]:
            for p in pages:
                if not p["in_sitemap"] and not p["noindex"]:
                    issue("not_in_sitemap", "low", "Sitemap", "Indexable pages missing from the sitemap",
                          "Add them to the sitemap.", p["url"])
    elif not data["sitemap"]["files"]:
        issue("no_sitemap", "medium", "Sitemap", "No XML sitemap found",
              "Publish /sitemap.xml and reference it in robots.txt.", data["root"])
    if not data["robots"]["found"]:
        issue("no_robots", "low", "Technical", "No robots.txt found",
              "Add a robots.txt that references your sitemap.", data["root"])
    for u in data["blocked"][:50]:
        issue("blocked", "low", "Indexing", "URLs blocked by robots.txt (skipped by this crawl)",
              "Make sure these are blocked on purpose.", u)

    issue_list = []
    for it in issues.values():
        it["count"] = len(it["items"])
        it["items"] = it["items"][:100]
        issue_list.append(it)
    issue_list.sort(key=lambda i: (SEV_ORDER[i["severity"]], -i["count"]))

    # ---- keyword decisions
    mappings = []
    for kw in keywords:
        kt = tokens(kw) or tokens(kw, keep_stop=True)
        scored = []
        for p in pages:
            s, found = score_page(kt, p["_idx"])
            p.setdefault("keyword_scores", {})[kw] = s
            scored.append((s, found, p))
        scored.sort(key=lambda x: (-x[0], -x[2]["inbound"]))
        mappings.append(keyword_report(kw, kt, scored, brand, by_url))

    for p in pages:
        sc = p.get("keyword_scores", {})
        p["best_keyword"] = max(sc, key=sc.get) if sc else ""

    # ---- structure
    types = defaultdict(list)
    sections = defaultdict(list)
    depth_counts = Counter()
    for p in pages:
        types[p["page_type"]].append(p)
        seg = p["path"].strip("/").split("/")[0]
        sections["/" + seg if seg else "/ (home)"].append(p)
        depth_counts["Not linked" if p["depth"] is None else p["depth"]] += 1
    architecture = {
        "page_types": [{"type": t, "count": len(v),
                        "examples": [{"url": x["url"], "path": x["path"]} for x in v[:6]]}
                       for t, v in sorted(types.items(), key=lambda kv: -len(kv[1]))],
        "sections": [{"section": s, "count": len(v),
                      "avg_words": round(sum(x["word_count"] for x in v) / len(v)),
                      "avg_inbound": round(sum(x["inbound"] for x in v) / len(v), 1)}
                     for s, v in sorted(sections.items(), key=lambda kv: -len(kv[1]))[:20]],
        "depth": [{"depth": k, "count": v} for k, v in sorted(
            depth_counts.items(), key=lambda kv: (kv[0] == "Not linked", kv[0] if kv[0] != "Not linked" else 0))],
        "most_linked": [{"url": p["url"], "path": p["path"], "inbound": p["inbound"], "title": p["title"]}
                        for p in sorted(pages, key=lambda x: -x["inbound"])[:10]],
        "orphans": [{"url": p["url"], "path": p["path"]} for p in pages
                    if p["depth"] is None and not in_all[p["url"]]][:50],
    }

    # ---- summary
    n_create = sum(m["decision"] == "CREATE" for m in mappings)
    n_opt = sum(m["decision"] == "OPTIMIZE" for m in mappings)
    n_comp = sum(m["decision"] == "CANNIBALIZATION" for m in mappings)
    n_ok = sum(m["decision"] == "STRONG" for m in mappings)
    n_high = sum(i["count"] for i in issue_list if i["severity"] == "high")
    summary = (f"Crawled {len(pages)} pages in {data['duration_s']} seconds. "
               + ("The page limit was reached, so this covers part of the site. " if data["truncated"] else "")
               + f"Of {len(mappings)} keyword(s): {n_create} need a new page, {n_opt} need optimizing, "
               f"{n_comp} have competing pages, {n_ok} are well targeted. "
               f"Found {len(issue_list)} issue types, {n_high} high-severity items.")

    stats = {
        "pages_analyzed": len(pages), "urls_discovered": data["urls_discovered"],
        "sitemap_urls": len(sm_urls), "failed": len(data["failed"]), "blocked": len(data["blocked"]),
        "thin": issues["thin"]["count"] if "thin" in issues else 0,
        "orphans": len(architecture["orphans"]),
        "noindex": sum(p["noindex"] for p in pages),
        "avg_words": round(sum(p["word_count"] for p in pages) / len(pages)),
    }

    out_pages = []
    for p in pages:
        out_pages.append({
            "url": p["url"], "path": p["path"], "status": p["status"], "title": p["title"],
            "h1": " | ".join(p["h1"]), "meta": p["meta"], "word_count": p["word_count"],
            "page_type": p["page_type"], "depth": p["depth"], "inbound": p["inbound"],
            "inbound_body": p["inbound_body"], "outbound": p["outbound"],
            "in_sitemap": p["in_sitemap"], "noindex": p["noindex"],
            "keyword_scores": p.get("keyword_scores", {}), "best_keyword": p["best_keyword"],
            "best_score": max(p.get("keyword_scores", {"": 0}).values()),
            "flags": p["flags"], "response_ms": p["elapsed_ms"],
        })

    return {
        "site": {"url": data["root"], "domain": base_key,
                 "analyzed_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())},
        "summary": summary, "stats": stats,
        "discovery": {"robots_txt": "found" if data["robots"]["found"] else "not found",
                      "crawl_delay": data["robots"]["crawl_delay"] or "none",
                      "sitemap_files": data["sitemap"]["files"], "sitemap_urls": len(sm_urls),
                      "urls_discovered": data["urls_discovered"], "crawl_limit_reached": data["truncated"],
                      "non_html_skipped": data["non_html_skipped"]},
        "keywords": mappings, "issues": issue_list, "pages": out_pages,
        "architecture": architecture,
    }


def _healthy(p):
    """A page only counts as 'well targeted' if nothing blocks or undermines it."""
    canon = normalize_url(urljoin(p["url"], p["canonical"])) if p["canonical"] else p["url"]
    return not p["noindex"] and canon == p["url"] and p["word_count"] >= 300


def keyword_report(kw, kt, scored, brand, by_url):
    intent = intent_of(kw)
    best_s, best_found, best = scored[0]
    second = scored[1] if len(scored) > 1 else None
    title_case = " ".join(w.capitalize() if w.islower() else w for w in kw.split())
    suggested_title = f"{title_case} | {brand}" if brand and len(title_case) + len(brand) + 3 <= 60 else title_case

    actions, warnings = [], []
    competing = []
    if best_s < 35:
        decision = "CREATE"
    elif second and second[0] >= 40 and second[0] >= best_s * 0.85:
        decision = "CANNIBALIZATION"
    elif best_s >= 70 and _healthy(best):
        decision = "STRONG"
    else:
        decision = "OPTIMIZE"

    related = [(s, p) for s, _f, p in scored if s >= 15 and p is not best][:5]

    if decision == "CREATE":
        actions.append(f"Create a new page that targets “{kw}”. No existing page is a strong match (best score {best_s}).")
        actions.append(f"Suggested title: {suggested_title}. Suggested H1: {title_case}.")
        if best_s >= 15:
            actions.append(f"Closest existing page is {best['path']} ({best_s}). Check it isn't already trying to cover this.")
        if related:
            actions.append("Once published, link to it from: " + ", ".join(p["path"] for _s, p in related[:4]) + ".")
    else:
        t = best
        if not best_found["title"]:
            actions.append(f"Put “{kw}” in the title tag" + (f" (now: “{t['title'][:70]}”)." if t["title"] else "."))
        if not best_found["h1"]:
            actions.append(f"Use “{kw}” in the H1" + (f" (now: “{t['h1'][0][:70]}”)." if t["h1"] else " — the page has no H1."))
        if not t["meta"]:
            actions.append("Add a meta description that mentions the keyword.")
        elif not best_found["meta"]:
            actions.append("Work the keyword into the meta description.")
        if t["word_count"] < 500:
            actions.append(f"The page is short ({t['word_count']} words). Add sections that answer what searchers want.")
        if not best_found["h2"] and t["h2"]:
            actions.append("Use the keyword (or a close variant) in at least one H2 subheading.")
        if t["inbound_body"] < 3:
            others = [p for _s, p in related if t["url"] not in p["_out"]][:4]
            n = t["inbound_body"]
            msg = ("No page links here from body content." if n == 0 else
                   f"Only {n} page{'s' if n != 1 else ''} link here from body content.")
            if others:
                msg += " Add links from: " + ", ".join(p["path"] for p in others) + "."
            actions.append(msg)
        if t["depth"] is not None and t["depth"] >= 4:
            actions.append(f"The page is {t['depth']} clicks from the homepage. Link it from navigation or a hub page.")
        if t["noindex"]:
            actions.append("The page is set to noindex, so it cannot rank. Remove the tag if it should.")
        if t["canonical"]:
            c = normalize_url(urljoin(t["url"], t["canonical"]))
            if c and c != t["url"]:
                actions.append(f"Its canonical tag points to {c}, so search engines may ignore this page.")
        if decision == "STRONG" and not actions:
            actions.append("Well targeted. Keep it fresh and keep internal links pointing here.")
        if decision == "CANNIBALIZATION":
            cands = [(s, p) for s, _f, p in scored[:4] if s >= 40]
            competing = [{"url": p["url"], "path": p["path"], "score": s, "inbound": p["inbound"]} for s, p in cands]
            primary = max(cands, key=lambda c: c[0] + min(10, c[1]["inbound"]))[1]
            actions.insert(0, f"{len(cands)} pages compete for “{kw}”. Suggested primary page: {primary['path']}. "
                              "Merge the others into it, differentiate their focus, or point their canonical at it, "
                              "then update internal links.")

    page_type = best["page_type"]
    expected = EXPECTED.get(intent)
    if decision != "CREATE" and expected and page_type not in expected:
        want = " or ".join(sorted(expected))
        warnings.append(f"This keyword looks {INTENT_LABEL[intent].lower()}, but the best match is a {page_type} page. "
                        f"A {want} page may fit the search intent better.")

    labels = {"CREATE": "Create a new page", "OPTIMIZE": "Optimize existing page",
              "STRONG": "Well targeted", "CANNIBALIZATION": "Pages compete"}
    headings = []
    for _s, p in [(best_s, best)] + related:
        for h in p["h2"]:
            if h and h not in headings:
                headings.append(h)
    return {
        "keyword": kw, "intent": INTENT_LABEL[intent], "decision": decision,
        "decision_label": labels[decision], "score": best_s,
        "target": None if decision == "CREATE" else {
            "url": best["url"], "path": best["path"], "title": best["title"], "page_type": page_type,
            "word_count": best["word_count"], "depth": best["depth"], "inbound": best["inbound"]},
        "closest": {"url": best["url"], "path": best["path"], "score": best_s},
        "found": best_found,
        "ranking": [{"url": p["url"], "path": p["path"], "title": p["title"], "score": s,
                     "page_type": p["page_type"]} for s, _f, p in scored[:5]],
        "actions": actions, "warnings": warnings, "competing": competing,
        "link_from": [{"url": p["url"], "path": p["path"], "score": s} for s, p in related],
        "related_headings": headings[:10],
        "suggested": {"title": suggested_title, "h1": title_case},
    }
