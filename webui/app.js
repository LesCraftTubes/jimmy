/* Jimmy — logique de l'interface web. Parle à Python par QWebChannel (objet « bridge »). Aucune dépendance externe. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
let bridge = null;
const S = { state: "loading", sessions: [], current: "", filter: "", level: 0, lastLevel: 0, prefs: {}, listening: false, muted: false,
            stepsBox: null, stepsCount: 0, live: null, liveQueue: [], stick: true, talkText: "Parler" };

const STATE_NAMES = { error: "Problème", loading: "Démarrage", wake: "En veille", idle: "Prêt", listening: "J'écoute", thinking: "Je travaille", speaking: "Je réponds", muted: "Micro coupé", sent: "Envoyé" };

/* ------------------------------------------------------------------ pont Python */
function call(name, ...args) { if (bridge && bridge[name]) { try { bridge[name](...args); } catch (e) { console.error(name, e); } } }
function connect() {
  if (typeof QWebChannel === "undefined" || !window.qt) { toast("Liaison avec Jimmy indisponible.", true); return; }
  new QWebChannel(qt.webChannelTransport, ch => {
    bridge = ch.objects.bridge;
    bridge.event.connect(raw => { try { onEvent(JSON.parse(raw)); } catch (e) { console.error(e, raw); } });
    bridge.ready();
  });
}

/* ------------------------------------------------------------------ markdown (petit, sûr) */
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function inline(t) {
  t = esc(t);
  t = t.replace(/`([^`\n]+)`/g, (_, c) => "<code>" + c + "</code>");
  t = t.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>").replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<i>$2</i>");
  t = t.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>');
  t = t.replace(/(^|[\s(>])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2">$2</a>');
  return t;
}
function markdown(src) {
  const blocks = []; src = src.replace(/\r\n/g, "\n");
  src = src.replace(/```([\w+#.\-]*)[^\n]*\n([\s\S]*?)```/g, (_, lang, code) => { blocks.push({ lang, code: code.replace(/\n$/, "") }); return "\n\u0000" + (blocks.length - 1) + "\u0000\n"; });
  const out = []; let list = null, para = [];
  const flushP = () => { if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; } };
  const flushL = () => { if (list) { out.push(`<${list.t}>` + list.items.map(i => "<li>" + inline(i) + "</li>").join("") + `</${list.t}>`); list = null; } };
  for (const line of src.split("\n")) {
    let m;
    if ((m = line.match(/^\u0000(\d+)\u0000$/))) { flushP(); flushL(); out.push(codeHtml(blocks[+m[1]])); continue; }
    if (/^\s*$/.test(line)) { flushP(); flushL(); continue; }
    if ((m = line.match(/^(#{1,3})\s+(.*)$/))) { flushP(); flushL(); out.push(`<h${m[1].length}>` + inline(m[2]) + `</h${m[1].length}>`); continue; }
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) { flushP(); flushL(); out.push("<hr>"); continue; }
    if ((m = line.match(/^\s*>\s?(.*)$/))) { flushP(); flushL(); out.push("<blockquote>" + inline(m[1]) + "</blockquote>"); continue; }
    if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) { flushP(); if (!list || list.t !== "ul") { flushL(); list = { t: "ul", items: [] }; } list.items.push(m[1]); continue; }
    if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) { flushP(); if (!list || list.t !== "ol") { flushL(); list = { t: "ol", items: [] }; } list.items.push(m[1]); continue; }
    flushL(); para.push(line);
  }
  flushP(); flushL();
  return out.join("");
}
function codeHtml(b) {
  return `<div class="codeblock"><div class="ch"><span>${esc(b.lang || "code")}</span><button data-copy>` +
    `<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>Copier</button></div>` +
    `<pre><code>${esc(b.code)}</code></pre></div>`;
}

/* ------------------------------------------------------------------ discussion */
const chat = $("#chat"), empty = $("#empty");
function refreshEmpty() { empty.classList.toggle("hidden", chat.children.length > 0); }
function scrollDown(force) { if (force || S.stick) chat.scrollTop = chat.scrollHeight; }
chat.addEventListener("scroll", () => {
  S.stick = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80;
  $("#toBottom").hidden = S.stick;
});
$("#toBottom").onclick = () => { S.stick = true; chat.scrollTop = chat.scrollHeight; };
chat.addEventListener("click", e => {
  const b = e.target.closest("[data-copy]");
  if (b) {
    const code = b.closest(".codeblock").querySelector("code").innerText;
    (navigator.clipboard ? navigator.clipboard.writeText(code) : Promise.reject()).catch(() => call("copyText", code));
    const old = b.lastChild.textContent; b.lastChild.textContent = "Copié"; setTimeout(() => b.lastChild.textContent = old, 1400);
    return;
  }
  const a = e.target.closest("a[href]");
  if (a) { e.preventDefault(); call("openUrl", a.getAttribute("href")); }
});
function closeSteps() { if (S.stepsBox) { S.stepsBox.classList.add("done"); const s = $("summary span.lbl", S.stepsBox); s.textContent = `Étapes (${S.stepsCount})`; S.stepsBox = null; S.stepsCount = 0; } }
function addMsg(role, text, label, color) {
  closeSteps();
  const d = document.createElement("div");
  if (role === "user") {
    d.className = "msg user"; d.innerHTML = `<div class="body"></div>`; $(".body", d).textContent = text;
  } else {
    d.className = "msg assistant"; d.style.setProperty("--c", color || "");
    d.innerHTML = `<div class="who"><i></i><b>${esc(label || "JIMMY")}</b></div><div class="body">${markdown(text)}</div>`;
  }
  chat.appendChild(d); refreshEmpty(); scrollDown(role === "user");
}
function addSystem(text) { closeSteps(); const d = document.createElement("div"); d.className = "sys"; d.innerHTML = "<span></span>"; $("span", d).textContent = text; chat.appendChild(d); refreshEmpty(); scrollDown(); }
function addStep(text, first) {
  if (!S.stepsBox || first) {
    closeSteps();
    const d = document.createElement("details"); d.className = "steps"; d.open = true;
    d.innerHTML = `<summary><i class="spin"></i><span class="lbl">Étapes</span></summary><div class="lines"></div>`;
    chat.appendChild(d); S.stepsBox = d; S.stepsCount = 0;
  }
  const [kind, ...rest] = text.split(" · "); const line = document.createElement("div");
  line.innerHTML = `<b></b><span></span>`; $("b", line).textContent = kind; $("span", line).textContent = rest.join(" · ");
  const lines = $(".lines", S.stepsBox); lines.appendChild(line); lines.scrollTop = lines.scrollHeight; S.stepsCount++;
  $("summary span.lbl", S.stepsBox).textContent = `Étapes (${S.stepsCount}) · ${kind}`;
  refreshEmpty(); scrollDown();
}
/* écriture en direct synchronisée avec la voix */
function liveBegin() {
  closeSteps();
  const d = document.createElement("div"); d.className = "msg assistant live"; d.style.setProperty("--c", "");
  d.innerHTML = `<div class="who"><i></i><b>JIMMY</b></div><div class="body"></div>`;
  chat.appendChild(d); S.live = { el: $(".body", d), root: d, shown: "" }; S.liveQueue = []; refreshEmpty(); scrollDown(true);
}
function liveChunk(text, duration) { if (!S.live) return; S.liveQueue.push({ text: text + " ", t0: performance.now(), dur: Math.max(300, duration * 1000), done: 0 }); requestAnimationFrame(livePump); }
function livePump() {
  if (!S.live) return; let more = false;
  while (S.liveQueue.length) {
    const c = S.liveQueue[0], upto = Math.min(c.text.length, Math.ceil(c.text.length * (performance.now() - c.t0) / c.dur));
    if (upto > c.done) { S.live.shown += c.text.slice(c.done, upto); c.done = upto; S.live.el.textContent = S.live.shown; scrollDown(); }
    if (c.done >= c.text.length) S.liveQueue.shift(); else { more = true; break; }
  }
  if (more) requestAnimationFrame(livePump);
}
function liveEnd(text, label, color) {
  if (S.live) { S.live.root.remove(); S.live = null; S.liveQueue = []; }
  addMsg("assistant", text, label, color);
}
function clearChat() { S.live = null; S.stepsBox = null; chat.innerHTML = ""; refreshEmpty(); S.stick = true; }

/* ------------------------------------------------------------------ orbe d'état (canvas) */
const orb = $("#orb"), octx = orb.getContext("2d");
let orbT = 0;
function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#22d3ee"; }
function drawOrb(ts) {
  const w = orb.width, h = orb.height, cx = w / 2, cy = h / 2, st = S.state, t = ts / 1000;
  octx.clearRect(0, 0, w, h);
  const lvl = Math.min(1, S.level * 14); S.level *= 0.88;
  const base = { loading: "#6b7490", wake: cssv("--accent"), idle: cssv("--accent"), listening: cssv("--ok"), thinking: cssv("--accent"), speaking: cssv("--accent2"), muted: cssv("--bad"), sent: cssv("--accent") }[st] || cssv("--accent");
  let r = w * 0.2, pulse = 0;
  if (st === "listening") pulse = lvl * 0.22; else if (st === "speaking") pulse = (0.08 + 0.07 * Math.sin(t * 9)) ; else if (st === "wake" || st === "idle") pulse = 0.03 * Math.sin(t * 1.6); else if (st === "thinking") pulse = 0.04 * Math.sin(t * 5);
  const g = octx.createRadialGradient(cx, cy, 2, cx, cy, w * 0.48);
  g.addColorStop(0, base + "ff"); g.addColorStop(0.45, base + "55"); g.addColorStop(1, base + "00");
  octx.fillStyle = g; octx.beginPath(); octx.arc(cx, cy, w * (0.36 + pulse), 0, 7); octx.fill();
  octx.fillStyle = base; octx.beginPath(); octx.arc(cx, cy, r * (1 + pulse * 1.6), 0, 7); octx.fill();
  octx.strokeStyle = base; octx.lineWidth = 3; octx.lineCap = "round";
  if (st === "thinking" || st === "loading") {
    for (let i = 0; i < 3; i++) { const a = t * (st === "loading" ? 1.2 : 3.2) + i * 2.09; octx.globalAlpha = 0.9 - i * 0.25; octx.beginPath(); octx.arc(cx, cy, w * 0.36, a, a + 1.1); octx.stroke(); }
    octx.globalAlpha = 1;
  } else if (st === "speaking") {
    for (let i = 0; i < 5; i++) { const hh = (0.12 + 0.34 * Math.abs(Math.sin(t * 6 + i * 1.3))) * h * 0.5, x = cx + (i - 2) * 9; octx.beginPath(); octx.moveTo(x, cy - hh * 0.5); octx.lineTo(x, cy + hh * 0.5); octx.stroke(); }
  } else if (st === "listening") {
    octx.globalAlpha = 0.5; octx.beginPath(); octx.arc(cx, cy, w * (0.38 + lvl * 0.1), 0, 7); octx.stroke(); octx.globalAlpha = 1;
  }
  requestAnimationFrame(drawOrb);
}
requestAnimationFrame(drawOrb);

/* ------------------------------------------------------------------ état, micro, statut */
function setState(st) {
  S.state = st; const pill = $("#statusPill"); pill.dataset.state = st; pill.classList.remove("warn");
  $("#stateName").textContent = STATE_NAMES[st] || st;
  updateTalk();
}
function updateTalk() {
  const b = $("#btnTalk"), listening = S.state === "listening";
  const flowing = performance.now() - S.lastLevel < 2500;
  b.classList.toggle("active", listening && flowing); b.classList.toggle("warn", listening && !flowing); b.classList.toggle("muted", S.muted);
  $("#talkText").textContent = listening ? (flowing ? "J'écoute…" : "Micro silencieux…") : "Parler";
  if (listening && !flowing) $("#statusPill").classList.add("warn");
  $("#btnMute").setAttribute("aria-pressed", S.muted ? "true" : "false");
}
setInterval(updateTalk, 700);   /* le bouton ne ment jamais : « J'écoute » seulement si du son arrive vraiment */

/* ------------------------------------------------------------------ discussions (barre latérale) */
function renderSessions() {
  const box = $("#sessions"); box.innerHTML = ""; const f = S.filter.toLowerCase();
  for (const s of S.sessions) {
    if (f && !s.title.toLowerCase().includes(f)) continue;
    const d = document.createElement("div"); d.className = "session" + (s.id === S.current ? " active" : "") + (s.full ? " full" : ""); d.title = s.title;
    d.innerHTML = `<div class="t"></div><div class="w"></div><div class="acts"><button data-a="ren" title="Renommer"><svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg></button><button data-a="del" title="Supprimer"><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg></button></div>`;
    $(".t", d).textContent = s.title; $(".w", d).textContent = s.when + (s.full ? "  ·  pleine" : "");
    d.onclick = e => { const a = e.target.closest("[data-a]"); if (a) { e.stopPropagation(); call(a.dataset.a === "ren" ? "renameSession" : "deleteSession", s.id); } else call("openSession", s.id); };
    box.appendChild(d);
  }
}
$("#searchSessions").oninput = e => { S.filter = e.target.value; renderSessions(); };

/* ------------------------------------------------------------------ envoi */
const input = $("#input");
function fit() { input.style.height = "auto"; input.style.height = Math.min(220, input.scrollHeight) + "px"; }
input.addEventListener("input", fit);
function send() { const t = input.value.trim(); if (!t) return; input.value = ""; fit(); $("#preview").hidden = true; S.stick = true; call("send", t); }
input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
$("#btnSend").onclick = send;
$("#btnTalk").onclick = () => call("talk");
$("#btnMute").onclick = () => { S.muted = !S.muted; updateTalk(); call("mute", S.muted); };
$("#btnStop").onclick = () => call("stop");
$("#btnNew").onclick = () => call("newChat");
$("#btnCC").onclick = () => call("openCC");
$("#btnMobile").onclick = () => call("openMobile");
$("#btnFolder").onclick = () => call("pickFolder");
$("#btnSettings").onclick = () => call("openSettings");
$("#btnRestart").onclick = () => call("restartApp");
$("#btnVoiceTest").onclick = () => call("voiceTest");
$("#selVoice").onchange = e => call("voicePreset", e.target.value);
$("#selModel").onchange = e => call("setCost", "model", e.target.value);
$("#selEffort").onchange = e => call("setCost", "effort", e.target.value);
$$("#routeSeg button").forEach(b => b.onclick = () => { setRoute(b.dataset.v); call("setRoute", b.dataset.v); });
function setRoute(v) { $$("#routeSeg button").forEach(b => b.classList.toggle("on", b.dataset.v === v)); }
$$("#voiceMenu input[data-k]").forEach(i => i.onchange = () => call("toggle", i.dataset.k, i.checked));
const vm = $("#voiceMenu");
$("#btnVoiceMenu").onclick = e => { e.stopPropagation(); vm.hidden = !vm.hidden; };
document.addEventListener("click", e => { if (!vm.hidden && !e.target.closest(".menu-wrap")) vm.hidden = true; });
$("#btnTheme").onclick = () => { const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = t; try { localStorage.setItem("jimmy-theme", t); } catch (e) {} };
try { const t = localStorage.getItem("jimmy-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}

/* ------------------------------------------------------------------ préférences venues de Python */
function fillSelect(sel, items, current) { sel.innerHTML = ""; for (const [label, value] of items) { const o = document.createElement("option"); o.textContent = label; o.value = value; sel.appendChild(o); } sel.value = current; }
function applyPrefs(p) {
  S.prefs = p; const r = document.documentElement.style;
  r.setProperty("--accent", p.accent[0]); r.setProperty("--accent2", p.accent[1]); r.setProperty("--chat-size", (p.chat_font || 15) + "px");
  $("#version").textContent = "version " + p.version;
  fillSelect($("#selModel"), p.models, p.model || ""); fillSelect($("#selEffort"), p.efforts, p.effort || "");
  fillSelect($("#selVoice"), p.voices.map(v => [v, v]), p.voice_preset);
  $$("#voiceMenu input[data-k]").forEach(i => i.checked = !!p.toggles[i.dataset.k]);
  $("#routeSeg").hidden = !p.local_enabled; setRoute(p.route);
  $("#wakeWord").textContent = p.wake_label;
  document.body.classList.toggle("psy", !!p.psy);
}
function toast(text, err) { const t = document.createElement("div"); t.className = "toast" + (err ? " err" : ""); t.textContent = text; $("#toasts").appendChild(t); setTimeout(() => t.remove(), 7000); }

/* ------------------------------------------------------------------ événements Python -> page */
function onEvent(e) {
  switch (e.t) {
    case "prefs": applyPrefs(e.p); break;
    case "state": setState(e.state); break;
    case "status": $("#statusLbl").textContent = e.text; break;
    case "msg": e.role === "user" ? addMsg("user", e.text) : addMsg("assistant", e.text, e.label, e.color); break;
    case "system": addSystem(e.text); break;
    case "step": addStep(e.text, e.first); break;
    case "live_begin": liveBegin(); break;
    case "live_chunk": liveChunk(e.text, e.duration); break;
    case "live_end": liveEnd(e.text, e.label, e.color); break;
    case "clear": clearChat(); break;
    case "sessions": S.sessions = e.items; S.current = e.current; renderSessions(); break;
    case "usage": { const i = e.i, bar = $("#usageBar" + i); bar.style.width = e.pct + "%"; bar.style.background = e.color || ""; $("#usageText" + i).textContent = (e.text || "").replace(/^(Session|Semaine)\s*:\s*/, ""); break; }
    case "usage_title": $("#usageTitle").textContent = e.text; break;
    case "ctx": { $("#ctxLbl").textContent = e.label; const b = $("#ctxBar"); b.style.width = e.pct + "%"; b.style.background = e.color || ""; $(".ctx").title = e.tip || ""; break; }
    case "folder": $("#folderLbl").textContent = e.text; break;
    case "level": S.level = Math.max(S.level, e.rms); S.lastLevel = performance.now(); $("#micLevel").style.width = Math.min(100, e.rms * 900) + "%"; break;
    case "preview": { const p = $("#preview"); p.textContent = e.text; p.hidden = !e.text; break; }
    case "append": input.value = (input.value ? input.value + " " : "") + e.text; fit(); input.focus(); break;
    case "placeholder": input.placeholder = e.text; break;
    case "talk": S.listening = !!e.active; updateTalk(); break;
    case "mute": S.muted = !!e.on; updateTalk(); break;
    case "restart_needed": $("#restartBanner").hidden = false; break;
    case "swap": chat.style.opacity = 0; requestAnimationFrame(() => { chat.style.transition = "opacity .45s"; chat.style.opacity = 1; setTimeout(() => chat.style.transition = "", 500); }); break;
    case "focus": input.focus(); break;
    case "toast": toast(e.text, e.err); break;
    case "psy": document.body.classList.toggle("psy", e.level > 0); break;
  }
}
window.addEventListener("load", () => { fit(); connect(); setTimeout(() => input.focus(), 300); });
