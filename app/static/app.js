const $ = id => document.getElementById(id);
let sessionId = null;
const PHASES = { start: "describe", clarify: "clarifying", questions: "questions", steps: "troubleshooting",
                 device_details: "device details",
                 resolved: "✅ resolved", escalated: "📋 escalated" };

$("user").value = localStorage.getItem("ts-user") || "";
$("user").addEventListener("change", () => localStorage.setItem("ts-user", $("user").value));

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = role === "bot" ? inlineMd(text) : esc(text);
  $("messages").appendChild(div);
  $("messages").scrollTop = $("messages").scrollHeight;
}
function addHtml(html) {
  const wrap = document.createElement("div"); wrap.innerHTML = html;
  $("messages").appendChild(wrap.firstElementChild);
  $("messages").scrollTop = $("messages").scrollHeight;
}
function setOptions(opts) {
  $("options").innerHTML = "";
  for (const o of opts) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = o;
    b.onclick = () => send(o); $("options").appendChild(b);
  }
}
function renderState(r) {
  const s = r.state;
  $("s-cat").textContent = s.category_label || "–";
  $("s-phase").textContent = PHASES[s.phase] || s.phase;
  $("s-pri").innerHTML = s.priority ? priBadge(s.priority) : "–";
  $("s-step").textContent = s.step ? `step ${s.step} of ${s.total_steps}` : "–";
  const d = s.device || {};
  $("s-dev").textContent = [d.device_type, d.os, d.model_asset].filter(Boolean).join(" · ") || "–";
  $("articles").innerHTML = r.articles.length ? r.articles.map(a =>
    `<a class="article" data-id="${esc(a.id)}">${esc(a.title)}<small>${esc(a.category)}${a.score != null ? " · relevance " + a.score : ""}</small></a>`).join("")
    : "No matching articles yet.";
  document.querySelectorAll(".article").forEach(el => el.onclick = () => openArticle(el.dataset.id));
  $("mode").textContent = r.llm ? "LLM + retrieval" : "rules + retrieval";
}
async function send(text) {
  text = text.trim(); if (!text) return;
  addMsg("user", text); setOptions([]); $("input").value = "";
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId, user: $("user").value || null }) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const r = await res.json();
    sessionId = r.session_id;
    addMsg("bot", r.reply);
    if (r.sources && r.sources.length) addHtml(sourcesHtml(r.sources));
    if (r.ticket && r.state.phase === "escalated") addHtml(ticketHtml(r.ticket));
    setOptions(r.options); renderState(r);
  } catch (e) { addMsg("bot", "⚠️ Couldn't reach the server: " + e.message); }
}
async function openArticle(id) {
  const a = await (await fetch(`/api/kb/${encodeURIComponent(id)}`)).json();
  $("modal-body").innerHTML = blockMd(a.body); $("modal").classList.add("open");
}
function closeModal() { $("modal").classList.remove("open"); }
$("modal").onclick = e => { if (e.target.id === "modal") closeModal(); };
$("composer").onsubmit = e => { e.preventDefault(); send($("input").value); };
function greet() {
  $("messages").innerHTML = ""; sessionId = null;
  addMsg("bot", "Hi! I'm your IT support assistant. Describe what's going wrong (for example *\"my laptop won't turn on\"* or *\"I can't print\"*) and I'll help you fix it, or create a ticket for a technician.");
  setOptions(["My computer won't turn on", "The printer isn't printing", "My laptop turns on, but the screen stays black", "No internet / Wi-Fi"]);
  renderState({ state: { phase: "start" }, articles: [], llm: false });
  fetch("/api/health").then(r => r.json()).then(h => $("mode").textContent = h.llm_enabled ? "LLM + retrieval" : "rules + retrieval");
}
$("new").onclick = greet;
greet();
