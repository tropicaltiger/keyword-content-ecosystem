
import re, json, time, hashlib
from urllib.parse import urljoin, urlparse, urldefrag, parse_qsl, urlencode
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string
from threading import Thread
from uuid import uuid4
from datetime import datetime, timezone
import traceback

app = Flask(__name__)
JOBS = {}
JOBS_LOCK = __import__('threading').Lock()
UA = "TechMakLabs-KeywordEcosystem/0.1 (+website-research)"
TIMEOUT = (4,4)
MAX_DEFAULT = 75
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Keyword Content Ecosystem — Real Research Engine</title>
<style>
:root{--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#e4e8ef;--blue:#2563eb;--green:#087f5b;--amber:#a15c00;--red:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#111827;color:#fff;padding:26px 5vw}header h1{margin:0 0 6px;font-size:27px}header p{margin:0;color:#cbd5e1}
main{max-width:1400px;margin:24px auto;padding:0 18px}.panel,.card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 5px 18px rgba(16,24,40,.04)}
.panel{padding:20px}.row{display:grid;grid-template-columns:2fr 1fr;gap:14px}.field{margin-bottom:13px}label{font-size:12px;font-weight:800;display:block;margin-bottom:6px}input,textarea{width:100%;border:1px solid #cbd5e1;border-radius:9px;padding:11px 12px;font:inherit}textarea{min-height:90px}
button{border:0;border-radius:9px;padding:11px 17px;font-weight:800;cursor:pointer}.primary{background:var(--blue);color:#fff}.secondary{background:#eef4ff;color:#1d4ed8}.tabs{display:flex;gap:7px;flex-wrap:wrap;margin:18px 0}.tab{background:#fff;border:1px solid var(--line);color:#475467}.tab.active{background:#111827;color:#fff}
.section{display:none}.section.active{display:block}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.stat{padding:16px}.stat b{display:block;font-size:24px}.stat span{font-size:11px;color:var(--muted)}
.card{padding:18px;margin-bottom:14px;overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid var(--line);font-size:12px;vertical-align:top}th{background:#fafafa;color:#667085;font-size:11px}.badge{padding:4px 7px;border-radius:999px;font-size:10px;font-weight:900;display:inline-block}.good{background:#e8f7ef;color:var(--green)}.warn{background:#fff3dc;color:var(--amber)}.bad{background:#feeceb;color:var(--red)}.muted{color:var(--muted);font-size:12px}.progress{height:8px;background:#edf0f4;border-radius:99px;overflow:hidden}.bar{height:100%;background:var(--blue);width:0}.notice{padding:12px;background:#fff8e6;border:1px solid #f1df9e;border-radius:9px;color:#6b5314;font-size:12px;margin-top:12px}.loading{display:none;margin-top:12px}.error{color:var(--red);font-weight:700}
@media(max-width:1000px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.row{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body><header><h1>Keyword Content Ecosystem</h1><p>Phase 2.2 — Real website research engine</p></header><main>
<div class="panel">
<div class="row"><div class="field"><label>WEBSITE URL</label><input id="url" placeholder="https://nims.ae"></div><div class="field"><label>MAX PAGES</label><input id="max" type="number" min="10" max="200" value="75"></div></div>
<div class="field"><label>TARGET KEYWORDS — 1 to 3, one per line</label><textarea id="keywords" placeholder="hse manpower dubai&#10;hse jobs training dubai&#10;hse dubai"></textarea></div>
<button class="primary" onclick="analyze()">Analyze Website</button>
<button class="secondary" onclick="loadNims()">Load NIMS Test</button>
<div class="loading" id="loading"><div>Researching website… <span id="msg">discovering URLs</span></div><div class="progress"><div class="bar" id="bar"></div></div></div>
<div class="notice">This version uses a real server-side crawler. It discovers robots.txt/sitemaps, follows same-domain internal links, normalizes URLs, extracts page signals, classifies pages and maps your keywords to existing URLs. No demo page data is injected into results.</div>
<div id="err" class="error"></div></div>

<div id="results" style="display:none">
<div class="tabs"><button class="tab active" data-tab="overview">Overview</button><button class="tab" data-tab="mapping">Keyword → URL</button><button class="tab" data-tab="pages">Pages</button><button class="tab" data-tab="gaps">Gaps & Issues</button><button class="tab" data-tab="architecture">Architecture</button><button class="tab" data-tab="json">JSON</button></div>
<section class="section active" id="overview"><div class="cards" id="stats"></div><div class="card"><h3>Research summary</h3><div id="summary"></div></div><div class="card"><h3>Discovery</h3><div id="discovery"></div></div></section>
<section class="section" id="mapping"><div class="card"><h3>Keyword → URL decisions</h3><div id="mapping"></div></div></section>
<section class="section" id="pages"><div class="card"><h3>Analyzed pages</h3><div id="pages"></div></div></section>
<section class="section" id="gaps"><div class="card"><h3>Content / technical opportunities</h3><div id="gaps"></div></div></section>
<section class="section" id="architecture"><div class="card"><h3>Page-type architecture</h3><div id="architecture"></div></div></section>
<section class="section" id="json"><div class="card"><button class="secondary" onclick="downloadJSON()">Download research JSON</button><pre id="jsonbox"></pre></div></section>
</div></main>
<script>
let DATA=null;
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".section").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.getElementById(b.dataset.tab).classList.add("active")});
function loadNims(){document.getElementById("url").value="https://nims.ae";document.getElementById("keywords").value="hse manpower dubai\\nhse jobs training dubai\\nhse dubai";}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));}
function analyze(){
let url=document.getElementById("url").value.trim(), ks=document.getElementById("keywords").value.split(/\n|,/).map(x=>x.trim()).filter(Boolean).slice(0,3), max=+document.getElementById("max").value||150;
if(!url||!ks.length){document.getElementById("err").textContent="Enter a website and at least one keyword.";return}
document.getElementById("err").textContent="";document.getElementById("loading").style.display="block";document.getElementById("bar").style.width="15%";
fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,keywords:ks,max_pages:max})})
.then(async r=>{let raw=await r.text();let d;try{d=JSON.parse(raw)}catch(e){throw new Error("Server returned non-JSON response ("+r.status+"). Check Railway logs.")}if(!r.ok)throw new Error(d.error||"Analysis failed");return d})
.then(d=>pollJob(d.job_id))
.catch(e=>{document.getElementById("loading").style.display="none";document.getElementById("err").textContent=e.message});

function pollJob(jobId){
  const started=Date.now();
  const timer=setInterval(async()=>{
    try{
      const r=await fetch("/api/jobs/"+jobId);
      const d=await r.json();
      document.getElementById("bar").style.width=(d.progress||0)+"%";
      document.getElementById("msg").textContent=d.message||"researching";
      if(d.status==="complete"){
        clearInterval(timer);
        DATA=d.result; render(d.result);
        document.getElementById("bar").style.width="100%";
        setTimeout(()=>document.getElementById("loading").style.display="none",400);
      } else if(d.status==="failed"){
        clearInterval(timer);
        document.getElementById("loading").style.display="none";
        document.getElementById("err").textContent="Research failed: "+(d.message||"Unknown error");
      } else if(Date.now()-started>15*60*1000){
        clearInterval(timer);
        document.getElementById("err").textContent="Research is still running. You can check Railway logs; the job is running in the background.";
      }
    }catch(e){
      clearInterval(timer);
      document.getElementById("loading").style.display="none";
      document.getElementById("err").textContent="Could not read research status: "+e.message;
    }
  },1000);
}
}
function render(d){
document.getElementById("results").style.display="block";
let s=d.stats;document.getElementById("stats").innerHTML=[["URLs discovered",s.urls_discovered],["Pages analyzed",s.pages_analyzed],["Sitemap URLs",s.sitemap_urls],["Thin pages",s.thin_pages],["Missing metadata",s.missing_metadata],["Duplicates",s.duplicate_titles]].map(x=>`<div class="card stat"><b>${x[1]}</b><span>${x[0]}</span></div>`).join("");
document.getElementById("summary").innerHTML=`<p>${esc(d.summary)}</p><p class="muted">Site: ${esc(d.site.url)} · analyzed ${esc(d.site.analyzed_at)}</p>`;
document.getElementById("discovery").innerHTML=`<table><tr><th>Signal</th><th>Result</th></tr>${Object.entries(d.discovery).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(Array.isArray(v)?v.join(", "):v)}</td></tr>`).join("")}</table>`;
document.getElementById("mapping").innerHTML=`<table><tr><th>Keyword</th><th>Target URL</th><th>Score</th><th>Decision</th><th>Evidence</th></tr>${d.keyword_mapping.map(r=>`<tr><td><b>${esc(r.keyword)}</b></td><td>${r.url?`<a href="${esc(r.url)}" target="_blank">${esc(r.url)}</a>`:"—"}</td><td>${r.score}%</td><td><span class="badge ${r.decision==="CREATE"?"warn":"good"}">${esc(r.decision)}</span></td><td>${esc(r.evidence)}</td></tr>`).join("")}</table>`;
document.getElementById("pages").innerHTML=`<table><tr><th>URL</th><th>Type</th><th>Title</th><th>H1</th><th>Words</th><th>Keyword score</th><th>Flags</th></tr>${d.pages.map(p=>`<tr><td><a href="${esc(p.url)}" target="_blank">${esc(p.path)}</a></td><td>${esc(p.page_type)}</td><td>${esc(p.title)}</td><td>${esc(p.h1)}</td><td>${p.word_count}</td><td>${p.keyword_score}%</td><td>${p.flags.map(f=>`<span class="badge ${f.level}">${esc(f.label)}</span> `).join("")||"—"}</td></tr>`).join("")}</table>`;
document.getElementById("gaps").innerHTML=`<ul>${d.opportunities.map(x=>`<li style="margin:10px 0"><b>${esc(x.type)}</b> — ${esc(x.message)}</li>`).join("")}</ul>`;
document.getElementById("architecture").innerHTML=`<table><tr><th>Page type</th><th>Count</th><th>Examples</th></tr>${d.architecture.map(x=>`<tr><td>${esc(x.type)}</td><td>${x.count}</td><td>${x.examples.map(e=>`<a href="${esc(e.url)}" target="_blank">${esc(e.path)}</a>`).join("<br>")}</td></tr>`).join("")}</table>`;
document.getElementById("jsonbox").textContent=JSON.stringify(d,null,2);
}
function downloadJSON(){let b=new Blob([JSON.stringify(DATA,null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="keyword-ecosystem-research.json";a.click();URL.revokeObjectURL(a.href)}
</script></body></html>"""

def norm_url(url, base=None):
    if base: url=urljoin(base,url)
    url=urldefrag(url)[0]
    p=urlparse(url)
    if p.scheme not in ("http","https"): return None
    host=p.netloc.lower()
    path=p.path or "/"
    if path != "/" and path.endswith("/"): path=path.rstrip("/")
    qs=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
        if k.lower() not in {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","_ga"}]
    query=urlencode(qs)
    return f"{p.scheme}://{host}{path}" + (f"?{query}" if query else "")

def same_domain(a,b):
    return urlparse(a).netloc.lower().lstrip("www.") == urlparse(b).netloc.lower().lstrip("www.")

def get(url):
    try:
        r=SESSION.get(url,timeout=TIMEOUT,allow_redirects=True)
        return r
    except Exception:
        return None

def sitemap_urls(root):
    found=[]
    robots=get(urljoin(root,"/robots.txt"))
    if robots and robots.ok:
        for line in robots.text.splitlines():
            if line.lower().startswith("sitemap:"):
                u=line.split(":",1)[1].strip()
                if u: found.append(u)
    for p in ("/sitemap.xml","/sitemap_index.xml","/wp-sitemap.xml"):
        found.append(urljoin(root,p))
    return list(dict.fromkeys(found))

def parse_sitemap(url, seen=None):
    seen=seen or set()
    if url in seen or len(seen)>100: return []
    seen.add(url)
    r=get(url)
    if not r or not r.ok: return []
    text=r.text
    try:
        soup=BeautifulSoup(text,"xml")
    except Exception:
        return []
    locs=[x.get_text(strip=True) for x in soup.find_all("loc")]
    out=[]
    is_index=bool(soup.find("sitemapindex")) or "sitemap" in (soup.find().name if soup.find() else "")
    if is_index:
        for loc in locs: out.extend(parse_sitemap(loc,seen))
    else:
        out.extend(locs)
    return out

def classify(path,title="",text=""):
    s=(path+" "+title+" "+text[:500]).lower()
    if any(x in s for x in ["/blog","/news","/article","/insights"]): return "Blog / Article"
    if any(x in s for x in ["/case-study","/case-studies","/portfolio"]): return "Case Study"
    if any(x in s for x in ["/service","/services","/solutions"]): return "Service"
    if any(x in s for x in ["/training","/course","/courses","/certification"]): return "Training / Course"
    if any(x in s for x in ["/location","/dubai","/abu-dhabi","/sharjah","/ajman","/fujairah"]): return "Location"
    if any(x in s for x in ["/about","/contact","/careers","/career","/privacy","/terms"]): return "Company / Utility"
    return "General / Other"

def visible_text(soup):
    for x in soup(["script","style","noscript","svg","template"]): x.decompose()
    return re.sub(r"\s+"," ",soup.get_text(" ",strip=True))

def keyword_score(kw, page):
    text=(page["title"]+" "+page["meta"]+" "+page["h1"]+" "+page["h2"]+" "+page["text"]).lower()
    terms=[x for x in re.findall(r"[a-z0-9]+",kw.lower()) if len(x)>2]
    if not terms:return 0
    hits=sum(text.count(t) for t in terms)
    phrase=text.count(kw.lower())
    title=(page["title"]+" "+page["h1"]).lower()
    title_hits=sum(t in title for t in terms)
    score=min(100, round((hits/max(1,len(terms)*5))*45 + (phrase>0)*25 + (title_hits/max(1,len(terms)))*30))
    return score

def analyze_response(url, response, keywords):
    if not response or not response.ok or "text/html" not in response.headers.get("content-type","").lower():
        return None, []
    soup=BeautifulSoup(response.text,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    md=soup.find("meta",attrs={"name":re.compile("^description$",re.I)})
    meta=md.get("content","").strip() if md else ""
    h1=[x.get_text(" ",strip=True) for x in soup.find_all("h1")]
    h2=[x.get_text(" ",strip=True) for x in soup.find_all("h2")]
    canon=soup.find("link",rel=lambda v:v and "canonical" in v)
    canonical=canon.get("href","").strip() if canon else ""
    text=visible_text(soup)
    wc=len(re.findall(r"\b[\w’'-]+\b",text))
    p=urlparse(url)
    page={"url":url,"path":p.path or "/","title":title,"meta":meta,"h1":" | ".join(h1[:3]),
          "h2":" | ".join(h2[:8]),"canonical":canonical,"word_count":wc,
          "text":text[:12000]}
    scores=[keyword_score(k,page) for k in keywords]
    page["keyword_score"]=max(scores or [0])
    page["best_keyword"]=keywords[scores.index(max(scores))] if scores else ""
    page["page_type"]=classify(p.path,title,text)
    flags=[]
    if not title: flags.append({"label":"NO TITLE","level":"bad"})
    if not h1: flags.append({"label":"NO H1","level":"bad"})
    if not meta: flags.append({"label":"NO META","level":"warn"})
    if wc<300: flags.append({"label":"THIN","level":"warn"})
    if len(h1)>1: flags.append({"label":"MULTIPLE H1","level":"warn"})
    page["flags"]=flags

    links=[]
    for a in soup.find_all("a",href=True):
        nu=norm_url(a["href"],url)
        if nu:
            links.append(nu)
    return page, links

def crawl(root, keywords, max_pages):
    root=norm_url(root)
    if not root: raise ValueError("Invalid URL")
    base=f"{urlparse(root).scheme}://{urlparse(root).netloc}"
    smaps=sitemap_urls(base)
    sm_urls=[]
    for s in smaps:
        sm_urls.extend(parse_sitemap(s))
    sm_urls=[norm_url(x) for x in sm_urls if x and same_domain(x,base)]
    queue=list(dict.fromkeys(sm_urls+[root]))
    seen=set(); pages=[]; failed=[]
    i=0
    while i<len(queue) and len(pages)<max_pages:
        u=norm_url(queue[i]); i+=1
        if not u or u in seen or not same_domain(u,base): continue
        seen.add(u)
        r=get(u)
        pg, links=analyze_response(u,r,keywords)
        if not pg:
            failed.append({"url":u,"reason":"not HTML / request failed / non-2xx"})
            continue
        pages.append(pg)
        for nu in links:
            if nu not in seen and same_domain(nu,base) and len(queue)<max_pages*5:
                if not re.search(r"\.(pdf|jpg|jpeg|png|gif|webp|svg|zip|docx?|xlsx?|pptx?|mp4|mp3)($|\?)",urlparse(nu).path.lower()):
                    queue.append(nu)
    return root,smaps,sm_urls,queue,pages,failed

def duplicate_count(pages,key):
    vals=[p[key].strip().lower() for p in pages if p[key].strip()]
    from collections import Counter
    return sum(n-1 for n in Counter(vals).values() if n>1)

@app.route("/")
def home(): return render_template_string(HTML)

@app.post("/api/analyze")
def api_analyze():
    data=request.get_json(force=True) or {}
    url=str(data.get("url","")).strip()
    keywords=[str(x).strip() for x in data.get("keywords",[]) if str(x).strip()][:3]
    max_pages=min(max(int(data.get("max_pages",MAX_DEFAULT)),10),200)
    if not url or not keywords:
        return jsonify(error="Website URL and at least one keyword are required."),400

    job_id=str(uuid4())
    with JOBS_LOCK:
        JOBS[job_id]={
            "id":job_id,"status":"queued","progress":0,
            "message":"Research queued","created_at":datetime.now(timezone.utc).isoformat()
        }

    def worker():
        try:
            with JOBS_LOCK:
                JOBS[job_id].update(status="running",progress=5,message="Discovering robots.txt and sitemaps")
            root,smaps,sm_urls,queue,pages,failed=crawl(url,keywords,max_pages)

            mappings=[]
            for kw in keywords:
                ranked=sorted(pages,key=lambda p:keyword_score(kw,p),reverse=True)
                best=ranked[0] if ranked else None
                second=ranked[1] if len(ranked)>1 else None
                score=keyword_score(kw,best) if best else 0
                if not best or score<35:
                    decision="CREATE"; evidence="No existing page has a strong relevance score."
                elif second and score-second["keyword_score"]<8 and second["keyword_score"]>=45:
                    decision="REVIEW / CANNIBALIZATION"; evidence=f"Top two pages are close: {best['path']} ({score}%) vs {second['path']} ({second['keyword_score']}%)."
                else:
                    decision="OPTIMIZE"; evidence=f"Existing {best['page_type'].lower()} page is the strongest match."
                mappings.append({"keyword":kw,"url":best["url"] if best and score>=35 else None,"score":score,"decision":decision,"evidence":evidence})

            opportunities=[]
            for p in pages:
                for f in p["flags"]:
                    opportunities.append({"type":f["label"],"message":p["path"]})
            for m in mappings:
                if m["decision"]=="CREATE":
                    opportunities.append({"type":"CONTENT GAP","message":f"No strong existing target for “{m['keyword']}”."})
                if m["decision"].startswith("REVIEW"):
                    opportunities.append({"type":"CANNIBALIZATION","message":f"Review competing URLs for “{m['keyword']}”."})

            from collections import defaultdict
            groups=defaultdict(list)
            for p in pages: groups[p["page_type"]].append(p)
            architecture=[]
            for typ,arr in sorted(groups.items(),key=lambda x:-len(x[1])):
                architecture.append({"type":typ,"count":len(arr),"examples":[{"url":x["url"],"path":x["path"]} for x in arr[:8]]})

            result={
              "site":{"url":root,"analyzed_at":time.strftime("%Y-%m-%d %H:%M:%S UTC",time.gmtime())},
              "discovery":{"robots_or_sitemap_candidates":smaps,"sitemap_urls_found":len(sm_urls),"crawl_queue_discovered":len(set(queue)),"failed_or_skipped":len(failed),"same_domain":"yes"},
              "stats":{"urls_discovered":len(set(queue)),"pages_analyzed":len(pages),"sitemap_urls":len(sm_urls),"thin_pages":sum(any(f["label"]=="THIN" for f in p["flags"]) for p in pages),"missing_metadata":sum(any(f["label"]=="NO META" for f in p["flags"]) for p in pages),"duplicate_titles":duplicate_count(pages,"title")},
              "summary":f"Analyzed {len(pages)} HTML pages from the supplied domain. URL discovery used sitemap candidates plus same-domain internal links. Results are generated from the crawled site, not demo data.",
              "keyword_mapping":mappings,
              "pages":[{k:v for k,v in p.items() if k!="text"} for p in pages],
              "opportunities":opportunities[:300],
              "architecture":architecture,
              "failed_urls":failed[:100]
            }
            with JOBS_LOCK:
                JOBS[job_id].update(status="complete",progress=100,message="Research complete",result=result)
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id].update(status="failed",progress=100,message=str(e),error=traceback.format_exc())

    Thread(target=worker,daemon=True).start()
    return jsonify({"job_id":job_id,"status":"queued","message":"Research started"}),202


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    with JOBS_LOCK:
        job=JOBS.get(job_id)
        if not job:
            return jsonify(error="Job not found"),404
        return jsonify(job)


@app.get("/api/health")
def api_health():
    return jsonify(ok=True,service="keyword-content-ecosystem",active_jobs=sum(1 for j in JOBS.values() if j["status"] in ("queued","running")))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(__import__("os").environ.get("PORT",5000)))
