(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const link = (u, text) => /^https?:\/\//i.test(u)
    ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(text ?? u)}</a>` : esc(text ?? u);

  let DATA = null, jobId = null, timer = null, CFG = {}, cTimer = null, cJob = null;
  let KEY = sessionStorage.getItem("kce_key") || "";
  const sort = { key: "best_score", dir: -1 };
  let filter = "";

  const headers = () => ({ "Content-Type": "application/json", ...(KEY ? { "X-Access-Key": KEY } : {}) });

  // ---------------------------------------------------------------- setup
  fetch("/api/config").then(r => r.json()).then(c => {
    CFG = c;
    if (c.auth_required) { $("#keyRow").hidden = false; $("#key").value = KEY; }
  }).catch(() => {});

  $("#form").addEventListener("submit", e => { e.preventDefault(); start(); });
  $("#cancel").addEventListener("click", cancel);
  document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#dlJson").addEventListener("click", () => download("keyword-research.json", JSON.stringify(DATA, null, 2), "application/json"));
  $("#dlPages").addEventListener("click", () => download("pages.csv", pagesCsv(), "text/csv"));
  $("#dlIssues").addEventListener("click", () => download("issues.csv", issuesCsv(), "text/csv"));

  function showTab(name) {
    document.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll(".panel").forEach(p => { p.hidden = p.id !== "panel-" + name; });
  }

  function setError(msg) { $("#err").textContent = msg || ""; }
  function busy(on) {
    $("#run").disabled = on;
    $("#cancel").hidden = !on;
    $("#progress").hidden = !on;
  }

  // ---------------------------------------------------------------- job flow
  async function start() {
    setError("");
    if (!$("#keyRow").hidden) { KEY = $("#key").value.trim(); sessionStorage.setItem("kce_key", KEY); }
    const url = $("#url").value.trim();
    const keywords = $("#keywords").value.split("\n").map(x => x.trim()).filter(Boolean).slice(0, 5);
    const max_pages = parseInt($("#max").value, 10) || 75;
    if (!url || !keywords.length) return setError("Enter a website address and at least one keyword.");

    busy(true);
    $("#bar").style.width = "3%";
    $("#msg").textContent = "Starting";
    try {
      const r = await fetch("/api/analyze", { method: "POST", headers: headers(), body: JSON.stringify({ url, keywords, max_pages }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `The server returned an error (${r.status}).`);
      jobId = d.job_id;
      timer = setInterval(poll, 1000);
    } catch (e) { busy(false); setError(e.message); }
  }

  async function poll() {
    try {
      const r = await fetch("/api/jobs/" + jobId, { headers: headers() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Could not read progress.");
      $("#bar").style.width = (d.progress || 0) + "%";
      $("#msg").textContent = d.message || "";
      if (d.status === "complete") { stop(); DATA = d.result; render(DATA); }
      else if (d.status === "failed") { stop(); setError(d.message); }
      else if (d.status === "cancelled") { stop(); setError("Analysis cancelled."); }
    } catch (e) { stop(); setError(e.message); }
  }

  function stop() { clearInterval(timer); timer = null; busy(false); }

  async function cancel() {
    if (!jobId) return;
    await fetch("/api/jobs/" + jobId, { method: "DELETE", headers: headers() }).catch(() => {});
    $("#msg").textContent = "Cancelling";
  }

  // ---------------------------------------------------------------- render
  function render(d) {
    $("#empty").hidden = true;
    $("#results").hidden = false;
    $("#panel-overview").innerHTML = overview(d);
    $("#panel-keywords").innerHTML = d.keywords.map(keywordCard).join("");
    $("#panel-issues").innerHTML = issuesPanel(d);
    $("#panel-pages").innerHTML = pagesShell(d);
    bindPages();
    renderPagesTable();
    $("#panel-structure").innerHTML = structure(d.architecture);
    $("#jsonbox").textContent = JSON.stringify(d, null, 2);
    buildContentPanel(d);
    buildCompetitorsPanel(d);
    buildLinksPanel();
    showTab("keywords");
    window.scrollTo({ top: 0 });
  }

  function overview(d) {
    const s = d.stats, dc = d.discovery;
    const stat = (n, label) => `<div><b>${esc(n)}</b><span>${esc(label)}</span></div>`;
    const top = d.issues.slice(0, 5);
    return `
      <p class="lead">${esc(d.summary)}</p>
      <div class="stats">
        ${stat(s.pages_analyzed, "pages analyzed")}${stat(s.urls_discovered, "URLs discovered")}
        ${stat(s.sitemap_urls, "URLs in sitemap")}${stat(s.thin, "thin pages")}
        ${stat(s.orphans, "orphan pages")}${stat(s.failed, "broken URLs")}${stat(s.avg_words, "average words")}
      </div>
      <h3>Fix first</h3>
      ${top.length ? `<ul class="fixfirst">${top.map(i => `<li><span class="badge ${lvl(i.severity)}">${esc(i.severity)}</span>${esc(i.title)}<span class="n">${i.count} page${i.count === 1 ? "" : "s"}</span></li>`).join("")}</ul>` : `<p class="muted">No issues found.</p>`}
      <h3>How the site was read</h3>
      <div class="tablewrap"><table><tbody>
        <tr><td>Site</td><td>${link(d.site.url)}</td></tr>
        <tr><td>Analyzed</td><td>${esc(d.site.analyzed_at)}</td></tr>
        <tr><td>robots.txt</td><td>${esc(dc.robots_txt)}${dc.crawl_delay !== "none" ? `, crawl delay ${esc(dc.crawl_delay)}s` : ""}</td></tr>
        <tr><td>Sitemaps</td><td>${dc.sitemap_files.length ? dc.sitemap_files.map(f => link(f)).join("<br>") : "none found"}</td></tr>
        <tr><td>Page limit</td><td>${dc.crawl_limit_reached ? "Reached. Some pages were not crawled." : "Not reached. The whole site was covered."}</td></tr>
        <tr><td>Non-HTML files skipped</td><td>${dc.non_html_skipped}</td></tr>
      </tbody></table></div>`;
  }

  const lvl = sev => ({ high: "bad", medium: "warn", low: "note" }[sev] || "note");

  function keywordCard(k) {
    const f = k.found, t = k.target;
    const fieldChip = (ok, label) => `<li class="${ok ? "on" : "off"}">${label}${ok ? "" : " missing"}</li>`;
    const body = f.body_count > 0 ? `<li class="on">Body, ${f.body_count} time${f.body_count === 1 ? "" : "s"}</li>` : `<li class="off">Body missing</li>`;
    return `
    <article class="kw ${k.decision.toLowerCase()}">
      <div class="kw-head">
        <h3>${esc(k.keyword)}</h3>
        <span class="verdict">${esc(k.decision_label)}</span>
        <span class="intent">${esc(k.intent)} intent</span>
      </div>
      <div class="target">
        ${t ? `<span>Target page: ${link(t.url, t.path)}</span>` : `<span class="muted">No strong match. Closest: ${link(k.closest.url, k.closest.path)}</span>`}
        <span class="meter" title="Relevance score"><i><b style="width:${k.score}%"></b></i>${k.score}/100</span>
      </div>
      ${t ? `<ul class="chips" aria-label="Where the keyword appears">${fieldChip(f.title, "Title")}${fieldChip(f.h1, "H1")}${fieldChip(f.url, "URL")}${fieldChip(f.meta, "Meta description")}${fieldChip(f.h2, "H2")}${body}</ul>` : ""}
      ${k.warnings.map(w => `<p class="alert">${esc(w)}</p>`).join("")}
      <h4>What to do</h4>
      <ul class="list">${k.actions.map(a => `<li>${esc(a)}</li>`).join("")}</ul>
      ${k.competing.length ? `<h4>Competing pages</h4><div class="tablewrap"><table><thead><tr><th>Page</th><th class="num">Score</th><th class="num">Links in</th></tr></thead><tbody>${k.competing.map(c => `<tr><td class="path">${link(c.url, c.path)}</td><td class="num">${c.score}</td><td class="num">${c.inbound}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${k.link_from.length ? `<details><summary>Pages that should link to the target</summary><ul class="list">${k.link_from.map(p => `<li>${link(p.url, p.path)} <span class="muted small">relevance ${p.score}</span></li>`).join("")}</ul></details>` : ""}
      ${k.related_headings.length ? `<details><summary>Subtopics covered on related pages</summary><ul class="list">${k.related_headings.map(h => `<li>${esc(h)}</li>`).join("")}</ul></details>` : ""}
      <details><summary>Top matching pages</summary><div class="tablewrap"><table><thead><tr><th>Page</th><th>Type</th><th class="num">Score</th></tr></thead><tbody>${k.ranking.map(r => `<tr><td class="path">${link(r.url, r.path)}<span class="sub">${esc(r.title)}</span></td><td>${esc(r.page_type)}</td><td class="num">${r.score}</td></tr>`).join("")}</tbody></table></div></details>
    </article>`;
  }

  function issuesPanel(d) {
    if (!d.issues.length) return `<p class="muted">No issues found.</p>`;
    return d.issues.map(i => `
      <details class="issue">
        <summary><span class="badge ${lvl(i.severity)}">${esc(i.severity)}</span><span>${esc(i.title)} <span class="muted small">${esc(i.category)}</span></span><span class="n">${i.count} item${i.count === 1 ? "" : "s"}</span></summary>
        <div class="body">
          <p class="fix"><b>How to fix:</b> ${esc(i.fix)}</p>
          <ul>${i.items.map(x => `<li>${link(x.url)}${x.detail ? `<span>${esc(x.detail)}</span>` : ""}</li>`).join("")}</ul>
          ${i.count > i.items.length ? `<p class="muted small">Showing ${i.items.length} of ${i.count}. Download the CSV for the full list.</p>` : ""}
        </div>
      </details>`).join("");
  }

  // ---------------------------------------------------------------- pages table
  const COLS = [
    ["path", "Page"], ["page_type", "Type"], ["word_count", "Words", true], ["depth", "Depth", true],
    ["inbound", "Links in", true], ["weight_kb", "Size"], ["best_score", "Best keyword", true], ["flags", "Flags"],
  ];

  const fmtKB = kb => kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : kb + " KB";
  function sizeCell(p) {
    const s = p.size;
    if (!s || !s.weight_kb) return "–";
    const n = s.problems.length, worst = s.problems.some(x => x.severity === "high") ? "bad" : "warn";
    return `<details class="szd"><summary>${fmtKB(s.weight_kb)}${n ? ` <span class="badge ${worst}">${n} issue${n === 1 ? "" : "s"}</span>` : ""}</summary>
      <p class="small muted">HTML ${fmtKB(s.html_kb)}. Found ${s.counts.images} images, ${s.counts.scripts} scripts, ${s.counts.styles} stylesheets.${s.unmeasured ? ` ${s.unmeasured} files had no size information.` : ""}${s.measured ? "" : " Files were not measured."}</p>
      ${n ? `<ul class="list">${s.problems.map(x => `<li><b>${esc(x.title)}</b> (${esc(x.detail)}). ${esc(x.fix)}</li>`).join("")}</ul>` : `<p class="small">No size problems found.</p>`}
      ${s.savings_kb ? `<p class="small"><b>Could be reduced by roughly ${fmtKB(s.savings_kb)}</b> (a rough estimate).</p>` : ""}
      ${s.heavy_files.length ? `<p class="small muted">Heaviest files:</p><ul class="list small">${s.heavy_files.map(f => `<li>${fmtKB(f.kb)}, ${esc(f.kind)}: ${link(f.url, f.url.replace(/^https?:\/\/[^/]+/, "").slice(0, 70) || f.url)}</li>`).join("")}</ul>` : ""}</details>`;
  }

  function pagesShell() {
    const st = DATA.stats;
    return `<p class="muted small">Size is approximate: the page's HTML plus the images, scripts and stylesheets found in it (up to 250 files measured per crawl).${st.est_savings_kb ? ` Across the site, roughly <b>${fmtKB(st.est_savings_kb)}</b> could be saved. ${st.heavy_pages} page(s) are over 3 MB.` : ""} Open a size to see what is wrong and how to fix it.</p>
      <input id="pf" class="filter" type="search" placeholder="Filter by URL, title or type" aria-label="Filter pages">
      <div class="tablewrap"><table><thead><tr>${COLS.map(([k, label, num]) =>
        `<th class="${num ? "num" : ""}">${k === "flags" ? label : `<button type="button" data-sort="${k}">${label}</button>`}</th>`).join("")}</tr></thead>
      <tbody id="pbody"></tbody></table></div>`;
  }

  function bindPages() {
    $("#pf").addEventListener("input", e => { filter = e.target.value.toLowerCase(); renderPagesTable(); });
    document.querySelectorAll("[data-sort]").forEach(b => b.addEventListener("click", () => {
      const k = b.dataset.sort;
      sort.dir = sort.key === k ? -sort.dir : (k === "path" || k === "page_type" ? 1 : -1);
      sort.key = k;
      renderPagesTable();
    }));
  }

  function renderPagesTable() {
    const val = p => sort.key === "depth" ? (p.depth ?? 99) : p[sort.key];
    const rows = DATA.pages
      .filter(p => !filter || `${p.url} ${p.title} ${p.page_type}`.toLowerCase().includes(filter))
      .sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; });
    $("#pbody").innerHTML = rows.map(p => `<tr>
      <td class="path">${link(p.url, p.path)}<span class="sub">${esc(p.title || "(no title)")}</span></td>
      <td>${esc(p.page_type)}</td><td class="num">${p.word_count}</td>
      <td class="num">${p.depth ?? "–"}</td><td class="num">${p.inbound}<span class="sub">${p.inbound_body} in body</span></td><td>${sizeCell(p)}</td>
      <td>${p.best_keyword ? `${esc(p.best_keyword)} <span class="muted small">${p.best_score}</span>` : "–"}</td>
      <td>${p.flags.map(f => `<span class="badge ${f.level}">${esc(f.label)}</span>`).join("") || "–"}</td></tr>`).join("")
      || `<tr><td colspan="8" class="muted">No pages match.</td></tr>`;
  }

  // ---------------------------------------------------------------- structure
  function structure(a) {
    const max = Math.max(...a.depth.map(d => d.count), 1);
    const tbl = (head, rows) => `<div class="tablewrap"><table><thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
    return `
      <h3>Clicks from the homepage</h3>
      <div class="bars">${a.depth.map(d => `<div class="barrow"><span>${d.depth === "Not linked" ? "Not linked" : "Depth " + d.depth}</span><i><b style="width:${d.count / max * 100}%"></b></i><span>${d.count}</span></div>`).join("")}</div>
      <div class="cols">
        <div><h3>Page types</h3>${tbl(["Type", "Pages", "Examples"], a.page_types.map(t => `<tr><td>${esc(t.type)}</td><td>${t.count}</td><td class="path">${t.examples.slice(0, 3).map(e => link(e.url, e.path)).join("<br>")}</td></tr>`).join(""))}</div>
        <div><h3>Sections</h3>${tbl(["Section", "Pages", "Avg words", "Links in (all)", "Links in (body)"], a.sections.map(s => `<tr><td>${esc(s.section)}</td><td>${s.count}</td><td>${s.avg_words}</td><td>${s.avg_inbound}</td><td>${s.avg_inbound_body}</td></tr>`).join(""))}</div>
      </div>
      <div class="cols">
        <div><h3>Most linked pages</h3>${tbl(["Page", "Links in", "From body"], a.most_linked.map(p => `<tr><td class="path">${link(p.url, p.path)}</td><td>${p.inbound}</td><td>${p.inbound_body}</td></tr>`).join(""))}</div>
        <div><h3>Orphan pages</h3>${a.orphans.length ? tbl(["Page"], a.orphans.map(p => `<tr><td class="path">${link(p.url, p.path)}</td></tr>`).join("")) : `<p class="muted">None found. Every sitemap page is linked from another page.</p>`}</div>
      </div>`;
  }

  // ---------------------------------------------------------------- content plan
  const piece = (head, text, meta = "") => `<div class="piece"><div class="phead"><b>${esc(head)}</b><span class="meta">${meta}</span><button type="button" class="ghost" data-copy>Copy</button></div><pre>${esc(text)}</pre></div>`;
  const watch = w => (w && w.length) ? `<span class="badge warn">Reword: ${esc(w.join(", "))}</span>` : "";
  const cc = (n, max) => `<span class="badge ${n > max ? "bad" : "note"}">${n}/${max}</span>`;
  const CH = [["gbp", "Google Business Profile"], ["faq", "FAQs"], ["quora", "Quora"], ["reddit", "Reddit"], ["linkedin", "LinkedIn"], ["facebook", "Facebook"], ["pinterest", "Pinterest"]];

  document.addEventListener("click", e => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    navigator.clipboard.writeText(b.closest(".piece").querySelector("pre").textContent).then(() => {
      b.textContent = "Copied"; setTimeout(() => (b.textContent = "Copy"), 1200);
    });
  });

  function buildContentPanel(d) {
    const brand = d.facts.brand || "";
    $("#panel-content").innerHTML = `
      <h3>Who owns each keyword</h3><div id="ecoBox"></div>
      <h3>Where to work, and what is worth your time</h3>
      <div class="inline"><label>Business type
        <select id="ctype"><option value="local">Local business with customers in an area</option><option value="online">Online business or content site</option></select></label>
        <label>Country <select id="ccountry"><option>India</option><option>USA</option><option>UK</option><option>Canada</option><option value="">Other</option></select></label></div>
      <div id="playBox"></div>
      <h3>Write the content</h3>
      ${CFG.ai_enabled ? "" : `<p class="alert">AI writing is switched off. Add <b>ANTHROPIC_API_KEY</b> in your server settings to enable it. The map and playbook above work without it.</p>`}
      <form id="cform" class="cform" novalidate>
        <div class="inline">
          <label>Business name <input id="cname" value="${esc(brand)}"></label>
          <label>City or area <input id="ccity" placeholder="Madurai"></label>
        </div>
        <div class="inline">
          <label>Tone <select id="ctone"><option value="friendly">Friendly</option><option value="traditional">Warm and traditional</option><option value="professional">Professional</option><option value="direct">Direct and practical</option></select></label>
          <label>Language <input id="clang" value="English"></label>
        </div>
        <label>Facts the writer can use <span class="hint">strongly recommended: years in business, specialties, areas served, prices, what makes you different</span>
          <textarea id="cfacts" rows="4" placeholder="Family-run since 1998. Pure vegetarian. We serve Madurai and nearby towns. Weddings from 100 to 3000 guests."></textarea></label>
        <fieldset><legend>Channels</legend>${CH.map(([id, l]) => `<label class="check"><input type="checkbox" name="ch" value="${id}" ${["gbp", "faq"].includes(id) ? "checked" : ""}> ${l}</label>`).join("")}</fieldset>
        <button type="submit" class="primary" id="cgo" ${CFG.ai_enabled ? "" : "disabled"}>Write content</button>
        <span id="cmsg" class="muted small"></span>
      </form>
      <div id="cout"></div>`;
    $("#ctype").addEventListener("change", loadPlan);
    $("#ccountry").addEventListener("change", loadPlan);
    $("#cform").addEventListener("submit", e => { e.preventDefault(); writeContent(); });
    loadPlan();
  }

  async function loadPlan() {
    const r = await fetch(`/api/plan/${jobId}?type=${$("#ctype").value}&country=${encodeURIComponent($("#ccountry").value)}`, { headers: headers() });
    if (!r.ok) return;
    const p = await r.json();
    $("#ecoBox").innerHTML = `<div class="tablewrap"><table><thead><tr><th>Keyword</th><th>Verdict</th><th>Owner page</th><th>Link to it from</th><th>GBP posts and FAQ go to</th></tr></thead><tbody>${p.ecosystem.map(r => `<tr>
      <td>${esc(r.keyword)}<span class="sub">${esc(r.intent)} intent</span></td><td>${esc(r.decision)}</td>
      <td class="path">${r.has_owner ? link(r.owner, new URL(r.owner).pathname) : `<b>${esc(r.owner)}</b><span class="sub">Title: ${esc(r.suggested_title)}</span>`}</td>
      <td class="path">${r.link_from.length ? r.link_from.map(esc).join("<br>") : "–"}</td>
      <td class="path">${r.has_owner ? link(r.gbp_links_to, new URL(r.gbp_links_to).pathname) : esc(r.faq_goes_on)}</td></tr>`).join("")}</tbody></table></div>`;
    $("#playBox").innerHTML = p.playbook.map(x => `<details class="issue"><summary><span class="badge ${/Start/.test(x.priority) ? "good" : /Skip|Low/.test(x.priority) ? "note" : "warn"}">${esc(x.priority)}</span><span>${esc(x.name)}</span><span class="n">${esc(x.cadence)}</span></summary>
      <div class="body"><p class="fix"><b>Why:</b> ${esc(x.role)}</p><p><b>What to do:</b> ${esc(x.what)}</p><p><b>SEO honesty:</b> ${esc(x.seo_note)}</p>
      <ul>${x.do.map(t => `<li>Do: ${esc(t)}</li>`).join("")}${x.dont.map(t => `<li>Avoid: ${esc(t)}</li>`).join("")}</ul></div></details>`).join("");
  }

  async function writeContent() {
    const channels = [...document.querySelectorAll('input[name="ch"]:checked')].map(i => i.value);
    if (!channels.length) { $("#cmsg").textContent = "Pick at least one channel."; return; }
    $("#cgo").disabled = true; $("#cmsg").textContent = "Starting"; $("#cout").innerHTML = "";
    const body = { job_id: jobId, channels, business_name: $("#cname").value, city: $("#ccity").value, country: $("#ccountry").value,
      tone: $("#ctone").value, language: $("#clang").value, extra_facts: $("#cfacts").value };
    try {
      const r = await fetch("/api/content", { method: "POST", headers: headers(), body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Could not start writing.");
      cJob = d.job_id;
      cTimer = setInterval(pollContent, 1500);
    } catch (e) { $("#cmsg").textContent = e.message; $("#cgo").disabled = !CFG.ai_enabled; }
  }

  async function pollContent() {
    try {
      const r = await fetch("/api/jobs/" + cJob, { headers: headers() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Lost the writing job.");
      $("#cmsg").textContent = d.message || "";
      if (d.result) renderContent(d.result);
      if (["complete", "failed", "cancelled"].includes(d.status)) { clearInterval(cTimer); $("#cgo").disabled = !CFG.ai_enabled; if (d.status === "failed") $("#cmsg").textContent = d.message; }
    } catch (e) { clearInterval(cTimer); $("#cmsg").textContent = e.message; $("#cgo").disabled = !CFG.ai_enabled; }
  }

  function renderContent(res) {
    const out = [];
    CH.forEach(([id, label]) => {
      if (res.errors[id]) { out.push(`<section class="chan"><h3>${label}</h3><p class="error">${esc(res.errors[id])}</p></section>`); return; }
      const d = res.channels[id];
      if (!d) return;
      out.push(`<section class="chan"><h3>${label}</h3>${RENDER[id](d)}</section>`);
    });
    $("#cout").innerHTML = out.join("");
  }

  const posts = d => d.posts.map(p => piece(p.title, p.text + (p.cta ? `\n\nCall to action: ${p.cta}` : ""), watch(p.watch)) + (p.image_idea ? `<p class="muted small">Image: ${esc(p.image_idea)}</p>` : "")).join("");
  const RENDER = {
    gbp: d => `<h4>Business description ${cc(d.description.chars, 750)} ${watch(d.description.watch)}</h4>${piece("Description", d.description.text)}
      <h4>Posts</h4>${d.posts.map(p => piece(`${p.type}: ${p.topic}`, p.text, `${cc(p.chars, 1500)} ${watch(p.watch)}`) + `<p class="muted small">Button: ${esc(p.cta)}. Link to ${link(p.link_to, new URL(p.link_to).pathname)}. Photo: ${esc(p.photo_idea)}</p>`).join("")}
      <h4>Services to add to the profile</h4>${d.services.map(s => piece(s.name, s.description, cc(s.chars, 300))).join("")}
      ${d.photo_ideas.length ? `<h4>Photos to upload</h4><ul class="list">${d.photo_ideas.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`,
    faq: d => d.groups.map(g => `<h4>${esc(g.keyword)} <span class="muted small">put on ${link(g.page, new URL(g.page).pathname)}</span></h4>${g.faqs.map(f => piece(f.q, f.a, watch(f.watch))).join("")}`).join("")
      + `<h4>FAQ schema (JSON-LD)</h4><p class="muted small">Paste into the page. Google now shows FAQ rich results mainly for government and health sites, so the benefit is clarity for search engines and AI tools, not a guaranteed rich result.</p>${piece("FAQPage markup", d.jsonld)}`,
    quora: d => d.items.map(i => piece(i.question, i.answer + (i.mention ? `\n\n${i.mention}` : ""), watch(i.watch)) + `<p class="muted small">Find it: ${esc(i.search_tip)}</p>`).join(""),
    reddit: d => `<p class="alert">Reddit communities remove promotion fast. Use these to join conversations, not to advertise.</p>${d.posts.map(p => piece(p.title, p.body, esc(p.type) + " " + watch(p.watch))).join("")}
      <h4>Where to look</h4><ul class="list">${d.where.map(x => `<li>${esc(x)}</li>`).join("")}</ul><h4>Searches to find threads you can help with</h4><ul class="list">${d.listening.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`,
    linkedin: posts, facebook: posts,
    pinterest: d => d.pins.map(p => piece(p.title, p.description + `\nBoard: ${p.board}`, `${cc(p.title.length, 100)} ${cc(p.description.length, 500)} ${watch(p.watch)}`) + `<p class="muted small">Image: ${esc(p.image_idea)}. Link to ${link(p.link_to, new URL(p.link_to).pathname)}</p>`).join(""),
  };

  // ---------------------------------------------------------------- competitors
  const table = (head, rows) => `<div class="tablewrap"><table><thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
  const mapsLink = k => "https://www.google.com/maps/search/" + encodeURIComponent(k);
  const GBP_CHECK = ["Main category and extra categories (are rivals more specific?)", "Number of reviews, rating, and how recent the latest reviews are", "Whether the owner replies to reviews", "Services or products listed, with descriptions", "A clear, complete business description", "Number and quality of photos, and how recent they are", "How often they post updates or offers", "Opening hours, booking link and website link"];
  let compJob = null, compTimer = null, LAST_GAP = null;

  function buildCompetitorsPanel(d) {
    $("#panel-competitors").innerHTML = `
      <h3>Compare competitor websites</h3>
      <p class="muted">Add up to three competitors. Each is crawled (up to 30 pages) and checked against your keywords.</p>
      <form id="compform" class="cform"><div class="inline">${[1, 2, 3].map(n => `<label>Competitor ${n}<input id="comp${n}" placeholder="competitor${n}.com"></label>`).join("")}</div>
        <div><button type="submit" class="primary" id="compgo">Compare</button> <span id="compmsg" class="muted small"></span></div></form>
      <div id="compOut"></div>

      <h3>Backlink gap</h3>
      <p class="muted">Backlinks cannot be found by crawling, because they live in paid indexes. Instead, export each competitor's backlinks from a tool you have access to (the free backlink checkers from Ahrefs, Semrush or Moz show a limited list, which is enough to start) and paste or upload it here. Your own export is optional, and Google Search Console's Links report gives it free. The tool then shows sites that link to competitors but not to you.</p>
      <form id="blform" class="cform">
        <label>Your backlinks (optional) <textarea id="bl-you" rows="3" placeholder="Paste a CSV export, or just a list of URLs, one per line"></textarea><input type="file" data-fill="bl-you" accept=".csv,.txt"></label>
        <div class="inline">${[1, 2, 3].map(n => `<label>Competitor ${n} backlinks<textarea id="bl-c${n}" rows="4"></textarea><input type="file" data-fill="bl-c${n}" accept=".csv,.txt"></label>`).join("")}</div>
        <div><button type="submit" class="primary">Find link gaps</button> <span id="blmsg" class="muted small"></span></div></form>
      <div id="blOut"></div>

      <h3>Google Business Profile competition</h3>
      <div id="gbpBox">
        ${CFG.gbp_enabled ? `<form id="gbpform" class="cform"><label>Your business name on Google <span class="hint">helps find your listing in the results</span><input id="gbpname" value="${esc(d.facts.brand || "")}"></label>
          <div><button type="submit" class="primary">Check Google Business Profile competition</button> <span id="gbpmsg" class="muted small"></span></div></form>`
          : `<p class="alert">Automatic checks are off. They use Google's official Places API, which needs a <b>GOOGLE_PLACES_API_KEY</b> in your server settings. You can still compare by hand below.</p>`}
        <div id="gbpOut"></div>
        <h4>Compare by hand</h4>
        <ul class="list">${d.keywords.map(k => `<li>${link(mapsLink(k.keyword), "Search Google Maps for “" + k.keyword + "”")}</li>`).join("")}</ul>
        <p class="muted small">For the top three results, compare:</p><ul class="list small">${GBP_CHECK.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>`;
    $("#compform").addEventListener("submit", e => { e.preventDefault(); startCompare(); });
    $("#blform").addEventListener("submit", e => { e.preventDefault(); findGaps(); });
    document.querySelectorAll("[data-fill]").forEach(i => i.addEventListener("change", () => {
      const f = i.files[0]; if (!f) return;
      if (f.size > 1.5e6) { $("#blmsg").textContent = "That file is too large (limit 1.5 MB)."; return; }
      f.text().then(t => { $("#" + i.dataset.fill).value = t; });
    }));
    if ($("#gbpform")) $("#gbpform").addEventListener("submit", e => { e.preventDefault(); checkGbp(); });
  }

  async function startCompare() {
    const urls = [1, 2, 3].map(n => $("#comp" + n).value.trim()).filter(Boolean);
    if (!urls.length) { $("#compmsg").textContent = "Enter at least one competitor."; return; }
    $("#compgo").disabled = true; $("#compmsg").textContent = "Starting"; $("#compOut").innerHTML = "";
    try {
      const r = await fetch("/api/competitors", { method: "POST", headers: headers(), body: JSON.stringify({ job_id: jobId, urls }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Could not start.");
      compJob = d.job_id; compTimer = setInterval(pollComp, 1500);
    } catch (e) { $("#compmsg").textContent = e.message; $("#compgo").disabled = false; }
  }

  async function pollComp() {
    try {
      const r = await fetch("/api/jobs/" + compJob, { headers: headers() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Lost the comparison job.");
      $("#compmsg").textContent = d.message || "";
      if (d.result) renderComp(d.result);
      if (["complete", "failed", "cancelled"].includes(d.status)) { clearInterval(compTimer); $("#compgo").disabled = false; }
    } catch (e) { clearInterval(compTimer); $("#compmsg").textContent = e.message; $("#compgo").disabled = false; }
  }

  function renderComp(res) {
    $("#compOut").innerHTML = Object.entries(res.errors).map(([u, m]) => `<p class="error">${esc(u)}: ${esc(m)}</p>`).join("") + res.competitors.map(c => `
      <article class="kw optimize"><div class="kw-head"><h3>${esc(c.domain)}</h3><span class="intent">${c.pages} pages${c.crawl_limited ? " (crawl limited)" : ""}</span></div>
        <p class="muted small">Average ${c.avg_words} words per page. ${c.blog_posts} blog posts. FAQ markup on ${c.has_faq_schema} pages. LocalBusiness markup on ${c.has_local_schema} pages.</p>
        <h4>Their best page for each of your keywords</h4>
        ${table(["Keyword", "Verdict", "Their page", "Their words", "Your page", "Your words"], c.keywords.map(k => `<tr><td>${esc(k.keyword)}</td>
          <td><span class="badge ${k.verdict.startsWith("Their") ? "bad" : k.verdict.startsWith("Your") ? "good" : "note"}">${esc(k.verdict)}</span><span class="sub">${k.their_score} vs ${k.your_score}</span></td>
          <td class="path">${link(k.their_url, k.their_path)}<span class="sub">${esc(k.their_title)}</span></td><td>${k.their_words}</td><td class="path">${esc(k.your_path)}</td><td>${k.your_words}</td></tr>`).join(""))}
        ${c.topics_you_lack.length ? `<details><summary>Topics they cover that your site does not (${c.topics_you_lack.length})</summary><ul class="list">${c.topics_you_lack.map(t => `<li>${link(t.url, t.title || t.url)} <span class="muted small">${t.words} words</span></li>`).join("")}</ul></details>` : ""}
      </article>`).join("");
  }

  async function findGaps() {
    const comps = [1, 2, 3].map(n => ({ name: ($("#comp" + n)?.value.trim() || "Competitor " + n).replace(/^https?:\/\//, "").replace(/\/.*$/, ""), csv: $("#bl-c" + n).value })).filter(c => c.csv.trim());
    $("#blmsg").textContent = "Working";
    try {
      const r = await fetch("/api/backlinks", { method: "POST", headers: headers(), body: JSON.stringify({ job_id: jobId, yours: $("#bl-you").value, competitors: comps }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Could not read the exports.");
      LAST_GAP = d; $("#blmsg").textContent = "";
      $("#blOut").innerHTML = `<p class="lead">${d.total} sites link to your competitors but not to you. Showing the top ${d.prospects.length}, ordered by how many competitors they link to.</p>
        <p class="muted small">Sites read: ${Object.entries(d.competitor_domains).map(([n, c]) => `${esc(n)} (${c})`).join(", ")}${d.yours ? `, you (${d.yours})` : ""}. <button type="button" class="ghost" id="dlGap">Download CSV</button></p>
        ${table(["Site", "Links to", "Type", "How to approach"], d.prospects.map(p => `<tr><td class="path">${link("https://" + p.domain, p.domain)}</td><td>${p.count}: ${p.linked_to.map(esc).join(", ")}</td><td>${esc(p.kind)}</td><td>${esc(p.ease)}</td></tr>`).join(""))}`;
      $("#dlGap").addEventListener("click", () => download("backlink-gap.csv", toCsv([["domain", "competitors_linked", "linked_to", "type", "approach"], ...LAST_GAP.prospects.map(p => [p.domain, p.count, p.linked_to.join("; "), p.kind, p.ease])]), "text/csv"));
    } catch (e) { $("#blmsg").textContent = e.message; }
  }

  async function checkGbp() {
    $("#gbpmsg").textContent = "Asking Google";
    try {
      const r = await fetch("/api/gbp", { method: "POST", headers: headers(), body: JSON.stringify({ job_id: jobId, business_name: $("#gbpname").value }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Google check failed.");
      $("#gbpmsg").textContent = "";
      $("#gbpOut").innerHTML = d.results.map(k => `<h4>${esc(k.keyword)}</h4><ul class="list">${k.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>
        ${table(["#", "Business", "Category", "Rating", "Reviews", "Website"], k.places.map((p, i) => `<tr${p.is_you ? ' class="you"' : ""}><td>${i + 1}</td><td>${link(p.maps_url, p.name)}${p.is_you ? ' <span class="badge good">You</span>' : ""}<span class="sub">${esc(p.address)}</span></td><td>${esc(p.category)}</td><td>${p.rating ?? "–"}</td><td>${p.reviews}</td><td class="path">${p.website ? link(p.website, p.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")) : "–"}</td></tr>`).join(""))}`).join("") + `<p class="muted small">${esc(d.caveat)}</p>`;
    } catch (e) { $("#gbpmsg").textContent = e.message; }
  }

  // ---------------------------------------------------------------- links and directories
  function buildLinksPanel() {
    $("#panel-links").innerHTML = `
      <div class="inline"><label>Country <select id="lcountry"><option>India</option><option>USA</option><option>UK</option><option>Canada</option><option>Australia</option><option>UAE</option><option value="">Other</option></select></label>
      <label>Type of business <select id="lind"><option value="general">Any business</option><option value="health">Healthcare</option><option value="wedding">Weddings and events</option><option value="home">Home services</option><option value="b2b">B2B and industrial</option></select></label></div>
      <div id="linksOut"></div>`;
    $("#lcountry").addEventListener("change", loadLinks);
    $("#lind").addEventListener("change", loadLinks);
    loadLinks();
  }

  async function loadLinks() {
    const r = await fetch(`/api/resources?country=${encodeURIComponent($("#lcountry").value)}&industry=${$("#lind").value}`, { headers: headers() });
    if (!r.ok) return;
    const d = await r.json();
    const rows = list => list.map(x => `<tr><td class="path">${link(x.url, x.name)}</td><td>${esc(x.type)}</td><td>${esc(x.note)}</td></tr>`).join("");
    $("#linksOut").innerHTML = `
      <h3>Where to list your business</h3>
      ${d.region_known ? "" : `<p class="alert">I do not have a curated list for this country yet. The global listings below still apply, and the playbook on the Content plan tab suggests how to find local ones.</p>`}
      ${d.regional.length ? `<h4>For this region</h4>${table(["Directory", "Best for", "Note"], rows(d.regional))}` : ""}
      <h4>Worldwide</h4>${table(["Directory", "Best for", "Note"], rows(d.global))}
      <p class="muted small">${esc(d.note)}</p>
      <h3>Quickest legitimate ways to get backlinks</h3>
      <p class="muted">There is no safe shortcut to strong backlinks. These are ordered roughly from fastest to slowest.</p>
      <p class="alert">${esc(d.tip)}</p>
      ${d.strategies.map(s => `<details class="issue"><summary><span class="badge ${/Days|1 to 2/.test(s.speed) ? "good" : "warn"}">${esc(s.speed)}</span><span>${esc(s.name)}</span><span class="n">Link value: ${esc(s.quality)}</span></summary><div class="body"><p>${esc(s.how)}</p><p class="muted small">Effort: ${esc(s.effort)}</p></div></details>`).join("")}
      <h4>Avoid</h4><ul class="list">${d.avoid.map(a => `<li>${esc(a)}</li>`).join("")}</ul>
      <p class="muted small">Google treats paid and manipulative links as spam, which can lower your rankings.</p>`;
  }

  // ---------------------------------------------------------------- downloads
  function csvCell(v) {
    let s = String(v ?? "");
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;           // block spreadsheet formula injection
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }
  const toCsv = rows => rows.map(r => r.map(csvCell).join(",")).join("\n");

  function pagesCsv() {
    const kws = DATA.keywords.map(k => k.keyword);
    const head = ["url", "type", "title", "h1", "words", "depth", "links_in", "links_out", "in_sitemap", "noindex", ...kws.map(k => "score: " + k), "flags"];
    return toCsv([head, ...DATA.pages.map(p => [p.url, p.page_type, p.title, p.h1, p.word_count, p.depth ?? "", p.inbound, p.outbound, p.in_sitemap, p.noindex,
      ...kws.map(k => p.keyword_scores[k] ?? ""), p.flags.map(f => f.label).join("; ")])]);
  }

  function issuesCsv() {
    const rows = [["severity", "category", "issue", "url", "detail", "how_to_fix"]];
    DATA.issues.forEach(i => i.items.forEach(x => rows.push([i.severity, i.category, i.title, x.url, x.detail, i.fix])));
    return toCsv(rows);
  }

  function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }
})();
