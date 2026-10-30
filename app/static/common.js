// Tiny, safe markdown renderer (escape first, then a few inline/blocks rules).
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function inlineMd(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>").replace(/\[(\d)\]/g, '<span class="cite">$1</span>');
}
function blockMd(md) {
  const out = []; let list = null;
  for (const line of md.split("\n")) {
    let m;
    if ((m = line.match(/^(#{1,3})\s+(.*)/))) { close(); out.push(`<h${m[1].length + 1}>${inlineMd(m[2])}</h${m[1].length + 1}>`); }
    else if ((m = line.match(/^\d+\.\s+(.*)/))) { open("ol"); out.push(`<li>${inlineMd(m[1])}</li>`); }
    else if ((m = line.match(/^-\s+(.*)/))) { open("ul"); out.push(`<li>${inlineMd(m[1])}</li>`); }
    else if (line.trim()) { close(); out.push(`<p>${inlineMd(line)}</p>`); }
    else close();
  }
  close(); return out.join("");
  function open(t) { if (list !== t) { close(); out.push(`<${t}>`); list = t; } }
  function close() { if (list) { out.push(`</${list}>`); list = null; } }
}
function statusTag(s) { return `<span class="tag ${esc(s)}">${s === "approved" ? "✔ approved" : "uploaded · unreviewed"}</span>`; }
function sourcesHtml(sources) {
  if (!sources || !sources.length) return "";
  return `<div class="sources"><div class="muted">Sources</div>${sources.map(s => `<div class="source">
    <div class="t"><span class="cite">${s.n}</span> ${esc(s.title)} ${statusTag(s.status)}
      <span class="muted">${esc(s.section || "")} · score ${s.score}</span></div>
    <div class="snip">${esc(s.snippet)}</div></div>`).join("")}</div>`;
}
function priBadge(p) { return `<span class="pri ${esc(p)}">${esc(p)}</span>`; }
function ticketHtml(t, withJson = true) {
  const li = a => a.length ? a.map(x => `<li>${esc(x)}</li>`).join("") : "<li class='muted'>None</li>";
  const json = { ...t }; delete json.transcript;
  return `<div class="ticket-card">
    <h4>📋 ${esc(t.id)} ${priBadge(t.priority)} <span class="badge">${esc(t.status)}</span></h4>
    <div><strong>${esc(t.summary)}</strong></div>
    <div class="muted">User: ${esc(t.user)} · Category: ${esc(t.category)} · ${esc(new Date(t.created_at).toLocaleString())}</div>
    <div style="margin-top:8px"><strong>Device</strong><ul>${Object.entries(t.device || {}).map(([k, v]) =>
      `<li>${esc(k.replace("_", " "))}: ${esc(v)}</li>`).join("")}</ul></div>
    <div><strong>Symptoms</strong><ul>${li(t.symptoms)}</ul></div>
    <div><strong>Steps already tried</strong><ol>${li(t.steps_tried)}</ol></div>
    ${t.escalation && t.escalation.level ? `<div><strong>Recommended escalation</strong>
      <p style="margin:4px 0"><span class="badge">${esc(t.escalation.level)}</span> ${esc(t.escalation.reason)}</p></div>` : ""}
    <div><strong>Recommended next action</strong><p style="margin:4px 0">${esc(t.recommended_next_action)}</p></div>
    ${(t.sources || []).length ? `<div class="muted">Documentation cited: ${t.sources.map(d => esc(d.title) + " (" + esc(d.status) + ")").join(", ")}</div>` : ""}
    ${withJson ? `<details><summary class="muted">View JSON</summary><pre>${esc(JSON.stringify(json, null, 2))}</pre></details>` : ""}
  </div>`;
}
