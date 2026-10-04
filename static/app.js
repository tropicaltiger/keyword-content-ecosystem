(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  const link = (u, text) => /^https?:\/\//i.test(u)
    ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(text ?? u)}</a>` : esc(text ?? u);

  let DATA = null, jobId = null, timer = null;
  let KEY = sessionStorage.getItem("kce_key") || "";
  const sort = { key: "best_score", dir: -1 };
  let filter = "";

  const headers = () => ({ "Content-Type": "application/json", ...(KEY ? { "X-Access-Key": KEY } : {}) });

  // ---------------------------------------------------------------- setup
  fetch("/api/config").then(r => r.json()).then(c => {
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
    ["inbound", "Links in", true], ["best_score", "Best keyword", true], ["flags", "Flags"],
  ];

  function pagesShell() {
    return `<input id="pf" class="filter" type="search" placeholder="Filter by URL, title or type" aria-label="Filter pages">
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
      <td class="num">${p.depth ?? "–"}</td><td class="num">${p.inbound}</td>
      <td>${p.best_keyword ? `${esc(p.best_keyword)} <span class="muted small">${p.best_score}</span>` : "–"}</td>
      <td>${p.flags.map(f => `<span class="badge ${f.level}">${esc(f.label)}</span>`).join("") || "–"}</td></tr>`).join("")
      || `<tr><td colspan="7" class="muted">No pages match.</td></tr>`;
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
        <div><h3>Sections</h3>${tbl(["Section", "Pages", "Avg words", "Avg links in"], a.sections.map(s => `<tr><td>${esc(s.section)}</td><td>${s.count}</td><td>${s.avg_words}</td><td>${s.avg_inbound}</td></tr>`).join(""))}</div>
      </div>
      <div class="cols">
        <div><h3>Most linked pages</h3>${tbl(["Page", "Links in"], a.most_linked.map(p => `<tr><td class="path">${link(p.url, p.path)}</td><td>${p.inbound}</td></tr>`).join(""))}</div>
        <div><h3>Orphan pages</h3>${a.orphans.length ? tbl(["Page"], a.orphans.map(p => `<tr><td class="path">${link(p.url, p.path)}</td></tr>`).join("")) : `<p class="muted">None found. Every sitemap page is linked from another page.</p>`}</div>
      </div>`;
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
