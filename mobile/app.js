/* Jimmy mobile : se connecte à Jimmy sur ton PC (WebSocket). Aucune dépendance, aucun serveur tiers. */
(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* stockage indisponible */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* idem */ } },
  };

  let token = LS.get('jimmy.token', null);
  const opts = Object.assign({ tts: true, converse: false, awake: false, rate: 1.1 }, LS.get('jimmy.opts', {}));
  let ws = null, retry = 0, retryTimer = null;
  let connected = false, state = 'idle', busy = false;
  let awaiting = false;                 // une demande venant de CE téléphone attend sa réponse (seule celle-là est lue à voix haute)
  let listening = false, speaking = false, rec = null, lastHeard = '';
  let wakeLock = null;
  let sessions = [], current = '';

  // ------------------------------------------------------------------ orbe
  const orbs = Array.from(document.querySelectorAll('canvas.orb'));
  const COL = { idle: [34, 211, 238], listening: [255, 77, 109], thinking: [124, 58, 237], speaking: [74, 222, 128], off: [90, 100, 120] };
  const visState = () => !connected ? 'off' : listening ? 'listening' : speaking ? 'speaking' : state === 'thinking' ? 'thinking' : 'idle';
  function drawOrb(t) {
    const st = visState();
    const speed = st === 'thinking' ? 0.006 : st === 'listening' ? 0.008 : 0.002;
    const amp = st === 'off' ? 0.02 : st === 'idle' ? 0.05 : 0.12;
    for (const c of orbs) {
      const [r, g, b] = COL[c.classList.contains('orb-big') ? 'idle' : st];   // l'orbe de l'écran de jumelage reste cyan
      const x = c.getContext('2d'), w = c.width, h = c.height, cx = w / 2, cy = h / 2;
      x.clearRect(0, 0, w, h);
      const pulse = 1 + Math.sin(t * speed * 3) * amp;
      const rad = Math.min(w, h) * 0.3 * pulse;
      const glow = x.createRadialGradient(cx, cy, rad * 0.2, cx, cy, rad * 2.3);
      glow.addColorStop(0, `rgba(${r},${g},${b},.55)`); glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
      x.fillStyle = glow; x.fillRect(0, 0, w, h);
      const core = x.createRadialGradient(cx - rad * 0.3, cy - rad * 0.3, rad * 0.1, cx, cy, rad);
      core.addColorStop(0, '#ffffff'); core.addColorStop(0.35, `rgb(${r},${g},${b})`); core.addColorStop(1, `rgba(${r >> 2},${g >> 2},${b >> 2},1)`);
      x.fillStyle = core; x.beginPath(); x.arc(cx, cy, rad, 0, Math.PI * 2); x.fill();
      x.strokeStyle = `rgba(${r},${g},${b},.65)`; x.lineWidth = Math.max(1.5, w / 70);
      for (let i = 0; i < 2; i++) {
        x.save(); x.translate(cx, cy); x.rotate(t * speed * (i ? -1.4 : 1) + i); x.scale(1, 0.38);
        x.beginPath(); x.arc(0, 0, rad * 1.55, 0, Math.PI * 2); x.stroke(); x.restore();
      }
    }
    requestAnimationFrame(drawOrb);
  }

  // ------------------------------------------------------------- affichage
  const chat = $('#chat');
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  function md(text) {
    let html = '';
    text.split('```').forEach((part, i) => {
      if (i % 2) {
        const nl = part.indexOf('\n');
        const code = (nl >= 0 ? part.slice(nl + 1) : part).replace(/\n$/, '');
        html += '<pre><button class="copy" type="button">Copier</button><code>' + esc(code) + '</code></pre>';
        return;
      }
      part.split(/\n{2,}/).forEach((par) => {
        par = par.trim();
        if (!par) return;
        const lines = par.split('\n');
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) html += '<ul>' + lines.map((l) => '<li>' + inline(l.replace(/^\s*[-*•]\s+/, '')) + '</li>').join('') + '</ul>';
        else html += '<p>' + lines.map(inline).join('<br>') + '</p>';
      });
    });
    return html;
  }
  function scrollDown() { chat.scrollTop = chat.scrollHeight; }
  function addBubble(role, text) {
    const d = document.createElement('div');
    d.className = 'm ' + role;
    if (role === 'assistant') d.innerHTML = md(text); else d.textContent = text;
    chat.appendChild(d);
    scrollDown();
  }
  chat.addEventListener('click', (e) => {
    const b = e.target.closest('button.copy');
    if (!b) return;
    const code = b.parentElement.querySelector('code').textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(code) : Promise.reject()).then(() => { b.textContent = 'Copié'; setTimeout(() => (b.textContent = 'Copier'), 1500); }).catch(() => {});
  });

  function ui() {
    const s = $('#status');
    s.classList.toggle('on', connected);
    s.textContent = !connected ? 'Hors ligne' : listening ? 'Je t’écoute…' : speaking ? 'Jimmy parle' : state === 'thinking' ? 'Jimmy travaille…' : 'En ligne · prêt';
    $('#offline').hidden = connected || !token;
    $('#working').hidden = !(connected && state === 'thinking');
    $('#btn-stop').hidden = !(connected && (state === 'thinking' || speaking));
    $('#btn-mic').classList.toggle('on', listening);
  }

  // ------------------------------------------------------------ connexion
  function showPair(msg) {
    $('#pair').hidden = false; $('#app').hidden = true;
    $('#pair-msg').textContent = msg || '';
  }
  function showApp() { $('#pair').hidden = true; $('#app').hidden = false; }

  function connect() {
    if (!token) { showPair(); return; }
    showApp();
    clearTimeout(retryTimer);
    if (ws && ws.readyState <= 1) return;
    const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    try { ws = new WebSocket(url); } catch { scheduleRetry(); return; }
    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
    ws.onmessage = (m) => { let ev; try { ev = JSON.parse(m.data); } catch { return; } onEvent(ev); };
    ws.onclose = () => { connected = false; ui(); scheduleRetry(); };
    ws.onerror = () => { try { ws.close(); } catch { /* déjà fermé */ } };
  }
  function scheduleRetry() {
    if (!token) return;
    clearTimeout(retryTimer);
    retry = Math.min(retry + 1, 6);
    retryTimer = setTimeout(connect, Math.min(1000 * 2 ** (retry - 1), 15000));
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      if (token && (!ws || ws.readyState > 1)) { retry = 0; connect(); }
      if (opts.awake && opts.converse) keepAwake();
    }
  });
  function send(obj) { if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; } return false; }

  function onEvent(ev) {
    switch (ev.type) {
      case 'denied':
        token = null; LS.del('jimmy.token'); showPair('Ce téléphone n’est plus relié. Scanne de nouveau le QR code.'); break;
      case 'sessions': setSessions(ev.items, ev.current); break;
      case 'hello':
        connected = true; retry = 0;
        chat.innerHTML = '';
        (ev.history || []).forEach((h) => { if (h.type === 'message') addBubble(h.role, h.text); else if (h.type === 'system') addBubble('system', h.text); });
        applyState(ev.state || {});
        setSessions((ev.state || {}).sessions, (ev.state || {}).current);
        $('#about').textContent = 'Relié à « ' + (ev.state && ev.state.pc ? ev.state.pc : 'ton PC') + ' » · ' + (ev.device || '');
        scrollDown(); ui();
        break;
      case 'state': applyState(ev); ui(); break;
      case 'message':
        addBubble(ev.role, ev.text);
        if (ev.role === 'assistant') afterReply(ev.text);
        break;
      case 'system': addBubble('system', ev.text); break;
      case 'step': {
        $('#working-text').textContent = ev.text;
        addBubble('step', ev.text);
        break;
      }
      case 'clear': chat.innerHTML = ''; break;
      default: break;
    }
  }
  function applyState(s) {
    state = s.state === 'thinking' ? 'thinking' : s.state === 'speaking' ? 'speaking-pc' : 'idle';
    busy = !!s.busy;
    if (state !== 'thinking') $('#working-text').textContent = 'Jimmy travaille…';
  }

  // ---------------------------------------------------------- discussions
  const firstLine = (t) => String(t || '').split(/\r?\n/)[0];
  function setSessions(items, cur) {
    sessions = Array.isArray(items) ? items : [];
    current = cur || '';
    const it = sessions.find((s) => s.id === current);
    const el = $('#convo');
    el.hidden = !it;
    el.textContent = it ? '• ' + firstLine(it.title) : '';
    if (!$('#convos').hidden) renderConvos();
  }
  function renderConvos() {
    const ul = $('#convo-list');
    ul.innerHTML = '';
    if (!sessions.length) { ul.innerHTML = '<li class="convo-empty" style="cursor:default;border:0;background:none">Aucune discussion pour le moment.</li>'; return; }
    sessions.forEach((s) => {
      const li = document.createElement('li');
      li.className = (s.id === current ? 'cur ' : '') + (s.full ? 'full' : '');
      const t = document.createElement('span'); t.className = 't'; t.textContent = firstLine(s.title);
      const w = document.createElement('span'); w.className = 'w'; w.textContent = s.when + (s.full ? ' · pleine' : '') + (s.id === current ? ' · en cours' : '');
      li.append(t, w);
      li.addEventListener('click', () => {
        $('#convos').hidden = true;
        if (s.id !== current) { stopSpeaking(); send({ type: 'switch', id: s.id }); }
      });
      ul.appendChild(li);
    });
  }
  function openConvos() { renderConvos(); $('#convos').hidden = false; }
  $('#btn-convos').addEventListener('click', openConvos);
  $('#btn-title').addEventListener('click', openConvos);
  $('#btn-close2').addEventListener('click', () => { $('#convos').hidden = true; });
  $('#convos').addEventListener('click', (e) => { if (e.target.id === 'convos') $('#convos').hidden = true; });
  $('#btn-new2').addEventListener('click', () => { send({ type: 'new' }); $('#convos').hidden = true; });

  // ---------------------------------------------------------------- voix
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const micOK = !!SR && window.isSecureContext;
  $('#btn-mic').hidden = !micOK;
  if (!micOK && SR) $('#input').placeholder = 'Écris à Jimmy (le micro demande une connexion sécurisée https)';

  function stopListening(sendIt) {
    if (!rec) return;
    const r = rec;
    if (!sendIt) lastHeard = '';
    try { r.stop(); } catch { /* déjà arrêté */ }
  }
  function startListening() {
    if (!micOK || listening || speaking) return;
    stopSpeaking();
    lastHeard = '';
    rec = new SR();
    rec.lang = 'fr-FR'; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
    rec.onstart = () => { listening = true; $('#live').hidden = false; $('#live').textContent = 'Parle…'; ui(); };
    rec.onresult = (e) => {
      let txt = '';
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
      lastHeard = txt.trim();
      $('#live').textContent = lastHeard || 'Parle…';
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        opts.converse = false; saveOpts(); addBubble('system', 'Micro refusé : autorise-le dans les réglages du navigateur.');
      }
    };
    rec.onend = () => {
      listening = false; rec = null;
      $('#live').hidden = true;
      const t = lastHeard; lastHeard = '';
      ui();
      if (t) sendText(t);
      else if (opts.converse && state !== 'thinking') setTimeout(startListening, 600);
    };
    try { rec.start(); } catch { listening = false; ui(); }
  }

  let voices = [];
  const loadVoices = () => { voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : []; };
  if (window.speechSynthesis) { loadVoices(); window.speechSynthesis.onvoiceschanged = loadVoices; }
  const frVoice = () => voices.find((v) => /^fr[-_]FR/i.test(v.lang) && /google|natural|online/i.test(v.name)) || voices.find((v) => /^fr/i.test(v.lang));
  const speakable = (t) => t.replace(/```[\s\S]*?```/g, ' ').replace(/`([^`]*)`/g, '$1').replace(/https?:\/\/\S+/g, ' ').replace(/[*_#>|]/g, ' ').replace(/\s+/g, ' ').trim();
  function stopSpeaking() { if (window.speechSynthesis) window.speechSynthesis.cancel(); if (speaking) { speaking = false; ui(); } }
  function speak(text, done) {
    const syn = window.speechSynthesis;
    const clean = speakable(text);
    if (!syn || !clean) { done && done(); return; }
    syn.cancel();
    const chunks = (clean.match(/[^.!?…]+[.!?…]*/g) || [clean]).map((c) => c.trim()).filter(Boolean);
    let i = 0;
    speaking = true; ui();
    const next = () => {
      if (!speaking) return;
      if (i >= chunks.length) { speaking = false; ui(); done && done(); return; }
      const u = new SpeechSynthesisUtterance(chunks[i++]);
      u.lang = 'fr-FR'; u.rate = opts.rate;
      const v = frVoice(); if (v) u.voice = v;
      u.onend = next; u.onerror = next;
      syn.speak(u);
    };
    next();
  }
  function afterReply(text) {
    if (!awaiting) return;              // réponse à une demande faite depuis le PC : on ne la lit pas ici
    awaiting = false;
    const again = () => { if (opts.converse) setTimeout(startListening, 500); };
    if (opts.tts && window.speechSynthesis) speak(text, again); else again();
  }

  async function keepAwake() {
    try { if ('wakeLock' in navigator && !wakeLock) { wakeLock = await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release', () => { wakeLock = null; }); } } catch { /* refusé */ }
  }
  function releaseAwake() { try { if (wakeLock) wakeLock.release(); } catch { /* rien */ } wakeLock = null; }

  // ------------------------------------------------------------- envoi
  function sendText(text) {
    text = (text || '').trim();
    if (!text) return;
    if (!connected) { addBubble('system', 'Pas de connexion au PC.'); return; }
    stopSpeaking();
    awaiting = true;
    send({ type: 'send', text });
  }
  $('#composer').addEventListener('submit', (e) => {
    e.preventDefault();
    const inp = $('#input');
    const t = inp.value;
    inp.value = ''; inp.style.height = 'auto';
    sendText(t);
  });
  $('#input').addEventListener('input', (e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'; });
  $('#input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !('ontouchstart' in window)) { e.preventDefault(); $('#composer').requestSubmit(); }
  });
  $('#btn-mic').addEventListener('click', () => { if (listening) stopListening(true); else { opts.converse = opts.converse; startListening(); } });
  $('#btn-stop').addEventListener('click', () => { stopSpeaking(); stopListening(false); send({ type: 'stop' }); awaiting = false; });

  // ---------------------------------------------------------- réglages
  function saveOpts() { LS.set('jimmy.opts', opts); }
  function syncSheet() {
    $('#opt-tts').checked = !!opts.tts; $('#opt-converse').checked = !!opts.converse;
    $('#opt-awake').checked = !!opts.awake; $('#opt-rate').value = opts.rate;
  }
  $('#btn-menu').addEventListener('click', () => { syncSheet(); $('#sheet').hidden = false; });
  $('#btn-close').addEventListener('click', () => { $('#sheet').hidden = true; });
  $('#sheet').addEventListener('click', (e) => { if (e.target.id === 'sheet') $('#sheet').hidden = true; });
  $('#opt-tts').addEventListener('change', (e) => { opts.tts = e.target.checked; saveOpts(); if (!opts.tts) stopSpeaking(); });
  $('#opt-converse').addEventListener('change', (e) => {
    opts.converse = e.target.checked; saveOpts();
    if (opts.converse) { $('#sheet').hidden = true; if (opts.awake) keepAwake(); startListening(); } else { stopListening(false); releaseAwake(); }
  });
  $('#opt-awake').addEventListener('change', (e) => { opts.awake = e.target.checked; saveOpts(); if (opts.awake && opts.converse) keepAwake(); else releaseAwake(); });
  $('#opt-rate').addEventListener('input', (e) => { opts.rate = parseFloat(e.target.value) || 1.1; saveOpts(); });
  $('#btn-new').addEventListener('click', () => { send({ type: 'new' }); $('#sheet').hidden = true; });
  $('#btn-unpair').addEventListener('click', () => {
    if (!confirm('Délier ce téléphone de Jimmy ?')) return;
    token = null; LS.del('jimmy.token'); try { ws && ws.close(); } catch { /* rien */ }
    $('#sheet').hidden = true; showPair('Téléphone délié.');
  });

  // ------------------------------------------------------------ jumelage
  function deviceName() {
    const ua = navigator.userAgent;
    const os = /iPhone|iPad/.test(ua) ? 'iPhone' : /Android/.test(ua) ? 'Android' : 'Téléphone';
    const br = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : '';
    return br ? os + ' (' + br + ')' : os;
  }
  async function pair(code) {
    const msg = $('#pair-msg'); msg.className = 'msg'; msg.textContent = 'Connexion…';
    try {
      const r = await fetch('/api/pair', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, name: deviceName() }) });
      const j = await r.json();
      if (!j.ok) { msg.textContent = j.error || 'Code refusé.'; return; }
      token = j.token; LS.set('jimmy.token', token);
      msg.className = 'msg ok'; msg.textContent = 'Relié !';
      retry = 0; connect();
    } catch { msg.textContent = 'Impossible de joindre le PC. Vérifie que Jimmy est ouvert.'; }
  }
  $('#pair-form').addEventListener('submit', (e) => { e.preventDefault(); const c = $('#pair-code').value.trim(); if (c) pair(c); });

  // --------------------------------------------------------------- départ
  requestAnimationFrame(drawOrb);
  const hm = /[#&]pair=([A-Za-z0-9]+)/.exec(location.hash);
  if (hm) { history.replaceState(null, '', location.pathname); $('#pair-code').value = hm[1]; token = null; LS.del('jimmy.token'); showPair(); pair(hm[1]); }
  else connect();
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
