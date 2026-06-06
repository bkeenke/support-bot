(function () {
  'use strict';

  // ── Config ──────────────────────────────────────────────────────────────────
  const script = document.currentScript;
  const cfg = window.__SW || {};

  const API = (
    script?.dataset.api || cfg.api ||
    (script?.src ? new URL(script.src).origin : '')
  ).replace(/\/$/, '');

  const USER_ID = script?.dataset.userId || cfg.userId || null;

  if (!API)     { console.warn('[SW] data-api required'); return; }
  if (!USER_ID) { console.warn('[SW] data-user-id required'); return; }

  const LANG = script?.dataset.lang || cfg.lang || document.documentElement.lang?.slice(0, 2) || 'ru';
  const I18N = {
    ru: { title: 'Поддержка', hint: 'Введите сообщение…', welcome: 'Привет! Чем можем помочь?' },
    en: { title: 'Support',   hint: 'Type a message…',    welcome: 'Hi! How can we help you?' },
  };
  const T = I18N[LANG] || I18N.ru;

  // ── Colors ──────────────────────────────────────────────────────────────────
  const PRIMARY = (script?.dataset.colorPrimary || cfg.colorPrimary || '#2563eb').toLowerCase();

  function _rgb(hex) {
    const h = hex.replace('#', '');
    const s = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
    const n = parseInt(s, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function _shade(hex, f) {   // f > 0 → darken, f < 0 → lighten toward white
    return '#' + _rgb(hex).map(c =>
      Math.min(255, Math.max(0, f > 0
        ? Math.round(c * (1 - f))
        : Math.round(c + (255 - c) * (-f))
      )).toString(16).padStart(2, '0')
    ).join('');
  }
  const P       = PRIMARY;
  const P_DARK  = script?.dataset.colorPrimaryDark  || cfg.colorPrimaryDark  || _shade(P,  0.15);
  const P_LIGHT = script?.dataset.colorPrimaryLight || cfg.colorPrimaryLight || _shade(P, -0.9);
  const P_DIS   = _shade(P, -0.45);   // disabled send button
  const [pr, pg, pb] = _rgb(P);
  const P_S1 = `rgba(${pr},${pg},${pb},.45)`;
  const P_S2 = `rgba(${pr},${pg},${pb},.55)`;

  // ── State ───────────────────────────────────────────────────────────────────
  const SID_KEY = 'sw:sid:' + USER_ID;
  let sid    = localStorage.getItem(SID_KEY) || null;
  let msgs   = [];   // [{ts, from:'bot'|'user'|'support', text?, photo_url?, file_url?, file_name?}]
  let offset = 0;    // how many messages already fetched
  let isOpen = false;
  let busy   = false;
  let unread = 0;
  let pollId = null;
  // Timestamps of user messages shown locally this session — used to skip duplicates from poll
  const pendingUserTs = [];

  const mk = (k) => `sw:${k}:${sid}`;

  function persist() {
    if (!sid) return;
    try {
      localStorage.setItem(mk('m'), JSON.stringify(msgs));
      localStorage.setItem(mk('o'), String(offset));
    } catch {}
  }

  function hydrate() {
    if (!sid) return;
    try { msgs = JSON.parse(localStorage.getItem(mk('m')) || '[]'); } catch { msgs = []; }
    offset = +(localStorage.getItem(mk('o')) || 0);
  }

  // ── API helpers ─────────────────────────────────────────────────────────────
  function authHdrs(extra = {}) {
    const h = { ...extra };
    if (sid) h['X-Session-Id'] = sid;
    return h;
  }

  async function apiInit() {
    const body = { user_id: +USER_ID };
    const r = await fetch(API + '/widget/session', {
      method: 'POST',
      headers: authHdrs({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!d.session_id) throw new Error('session error');
    sid = d.session_id;
    localStorage.setItem(SID_KEY, sid);
    hydrate();
    if (!msgs.length) {
      msgs.push({ ts: Date.now() / 1e3, from: 'bot', text: T.welcome });
      persist();
    }
  }

  async function apiSend(text) {
    const r = await fetch(API + '/widget/message', {
      method: 'POST',
      headers: authHdrs({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text }),
    });
    return (await r.json()).ok;
  }

  async function apiUpload(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(API + '/widget/upload', {
      method: 'POST',
      headers: authHdrs(),
      body: fd,
    });
    return (await r.json()).ok;
  }

  async function apiPoll() {
    const r = await fetch(`${API}/widget/messages?offset=${offset}`, {
      headers: authHdrs(),
    });
    return await r.json();
  }

  // ── CSS ─────────────────────────────────────────────────────────────────────
  function injectCSS() {
    if (document.getElementById('sw-css')) return;
    const el = document.createElement('style');
    el.id = 'sw-css';
    el.textContent = `
#sw-btn{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;
  background:${P};color:#fff;border:none;cursor:pointer;
  box-shadow:0 4px 20px ${P_S1};display:flex;align-items:center;
  justify-content:center;z-index:99998;transition:transform .2s,box-shadow .2s;}
#sw-btn:hover{transform:scale(1.08);box-shadow:0 6px 24px ${P_S2};}
#sw-badge{position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;padding:0 4px;
  border-radius:9px;background:#ef4444;color:#fff;font:700 10px/18px system-ui;
  display:none;align-items:center;justify-content:center;border:2px solid #fff;box-sizing:border-box;}
#sw-win{position:fixed;bottom:92px;right:24px;width:360px;height:520px;background:#fff;
  border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,.18);display:flex;flex-direction:column;
  overflow:hidden;z-index:99999;transform-origin:bottom right;
  transition:transform .2s cubic-bezier(.34,1.56,.64,1),opacity .15s;}
#sw-win.sw-hide{transform:scale(.88);opacity:0;pointer-events:none;}
.sw-head{background:${P};color:#fff;padding:14px 16px;display:flex;align-items:center;
  gap:8px;flex-shrink:0;font:600 15px/1 system-ui;}
.sw-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;flex-shrink:0;}
.sw-head-title{flex:1;}
.sw-close{background:none;border:none;color:rgba(255,255,255,.75);cursor:pointer;
  font-size:22px;line-height:1;padding:0;display:flex;align-items:center;}
.sw-close:hover{color:#fff;}
.sw-body{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;
  gap:6px;background:#f1f5f9;scroll-behavior:smooth;}
.sw-body::-webkit-scrollbar{width:4px;}
.sw-body::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:2px;}
.sw-bubble{max-width:82%;padding:9px 13px;border-radius:16px;font:14px/1.45 system-ui;
  word-break:break-word;animation:sw-in .2s ease;}
@keyframes sw-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.sw-bubble.sw-out{align-self:flex-end;background:${P};color:#fff;border-bottom-right-radius:4px;}
.sw-bubble.sw-in {align-self:flex-start;background:#fff;color:#1e293b;
  border-bottom-left-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.08);}
.sw-bubble img{max-width:100%;border-radius:8px;display:block;cursor:zoom-in;margin-top:4px;}
.sw-bubble a{color:inherit;text-decoration:underline;word-break:break-all;}
.sw-bubble .sw-fname{font-size:12px;opacity:.7;margin-top:2px;}
.sw-bubble .sw-time{font-size:11px;opacity:.5;margin-top:3px;text-align:right;}
.sw-foot{padding:10px 10px 12px;border-top:1px solid #e2e8f0;display:flex;
  gap:6px;align-items:flex-end;background:#fff;flex-shrink:0;}
#sw-input{flex:1;border:1.5px solid #e2e8f0;border-radius:20px;padding:9px 14px;
  font:14px/1.4 system-ui;resize:none;outline:none;max-height:96px;overflow-y:auto;
  background:#f8fafc;color:#1e293b;transition:border .15s;}
#sw-input:focus{border-color:${P};}
.sw-icon-btn{width:36px;height:36px;border:none;background:none;cursor:pointer;
  color:#94a3b8;display:flex;align-items:center;justify-content:center;
  border-radius:50%;flex-shrink:0;transition:background .15s,color .15s;}
.sw-icon-btn:hover{background:${P_LIGHT};color:${P};}
#sw-send{background:${P};color:#fff;transition:background .15s;}
#sw-send:hover{background:${P_DARK};color:#fff;}
#sw-send:disabled{background:${P_DIS};cursor:default;}
@media(max-width:420px){
  #sw-win{width:100vw;height:100dvh;bottom:0;right:0;border-radius:0;}
  #sw-btn{bottom:16px;right:16px;}
}`;
    document.head.appendChild(el);
  }

  // ── DOM builders ────────────────────────────────────────────────────────────
  let $body, $input, $send, $badge, $win;

  function svgChat() {
    return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
  }
  function svgSend() {
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
  }
  function svgAttach() {
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`;
  }

  function buildUI() {
    // Button
    const btn = document.createElement('button');
    btn.id = 'sw-btn';
    btn.setAttribute('aria-label', T.title);
    btn.innerHTML = svgChat();
    $badge = document.createElement('span');
    $badge.id = 'sw-badge';
    btn.appendChild($badge);
    btn.addEventListener('click', toggle);

    // Window
    $win = document.createElement('div');
    $win.id = 'sw-win';
    $win.classList.add('sw-hide');
    $win.innerHTML = `
      <div class="sw-head">
        <span class="sw-dot"></span>
        <span class="sw-head-title">${T.title}</span>
        <button class="sw-close" aria-label="Close">&#x2715;</button>
      </div>
      <div class="sw-body"></div>
      <div class="sw-foot">
        <button class="sw-icon-btn" id="sw-attach" title="Прикрепить файл">${svgAttach()}</button>
        <input type="file" id="sw-file" accept="image/*,application/pdf" style="display:none">
        <textarea id="sw-input" rows="1" placeholder="${T.hint}"></textarea>
        <button class="sw-icon-btn" id="sw-send" disabled>${svgSend()}</button>
      </div>`;

    $win.querySelector('.sw-close').addEventListener('click', toggle);

    document.body.appendChild(btn);
    document.body.appendChild($win);

    $body  = $win.querySelector('.sw-body');
    $input = $win.querySelector('#sw-input');
    $send  = $win.querySelector('#sw-send');
    const $attach = $win.querySelector('#sw-attach');
    const $file   = $win.querySelector('#sw-file');

    $attach.addEventListener('click', () => $file.click());
    $file.addEventListener('change', onFileChange);

    $input.addEventListener('input', () => {
      $input.style.height = 'auto';
      $input.style.height = Math.min($input.scrollHeight, 96) + 'px';
      $send.disabled = !$input.value.trim();
    });
    $input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
    });
    $send.addEventListener('click', onSend);

    renderAll();
  }

  // ── Rendering ───────────────────────────────────────────────────────────────
  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
  }

  function makeBubble(msg) {
    const el = document.createElement('div');
    const out = msg.from === 'user';
    el.className = 'sw-bubble ' + (out ? 'sw-out' : 'sw-in');
    let html = '';
    if (msg.photo_url) {
      html += `<img src="${msg.photo_url}" alt="photo" loading="lazy"
                onclick="window.open('${msg.photo_url}','_blank')">`;
    }
    if (msg.file_url) {
      html += `<a href="${msg.file_url}" target="_blank" rel="noopener">📎 ${msg.file_name || 'file'}</a>`;
    }
    if (msg.text) {
      html += (html ? '<br>' : '') + escHtml(msg.text).replace(/\n/g, '<br>');
    }
    html += `<div class="sw-time">${fmtTime(msg.ts)}</div>`;
    el.innerHTML = html;
    return el;
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function renderAll() {
    if (!$body) return;
    $body.innerHTML = '';
    msgs.forEach(m => $body.appendChild(makeBubble(m)));
    scrollBottom();
  }

  function appendMsg(msg) {
    if (!$body) return;
    $body.appendChild(makeBubble(msg));
    scrollBottom();
  }

  function scrollBottom() {
    if ($body) $body.scrollTop = $body.scrollHeight;
  }

  // ── Poll ────────────────────────────────────────────────────────────────────
  async function poll() {
    if (!sid || !isOpen) return;
    try {
      const d = await apiPoll();
      const newMsgs = Array.isArray(d.messages) ? d.messages : [];
      const serverTotal = typeof d.total === 'number' ? d.total : null;

      let added = 0;
      newMsgs.forEach(m => {
        if (m.from === 'user') {
          // Skip if we already rendered this locally (consume the pending entry)
          const idx = pendingUserTs.findIndex(t => Math.abs(t - m.ts) <= 3);
          if (idx !== -1) { pendingUserTs.splice(idx, 1); return; }
        }
        msgs.push(m);
        appendMsg(msgs[msgs.length - 1]);
        if (m.from !== 'user') unread++;
        added++;
      });

      if (serverTotal !== null) offset = serverTotal;
      else offset += newMsgs.length;

      if (added > 0 || serverTotal !== null) persist();
      updateBadge();
    } catch {}
  }

  function startPoll() { if (!pollId) pollId = setInterval(poll, 3000); }
  function stopPoll()  { clearInterval(pollId); pollId = null; }

  function updateBadge() {
    if (!$badge) return;
    $badge.style.display = unread > 0 ? 'flex' : 'none';
    $badge.textContent = unread > 9 ? '9+' : String(unread);
  }

  // ── Toggle ──────────────────────────────────────────────────────────────────
  async function toggle() {
    isOpen = !isOpen;
    $win.classList.toggle('sw-hide', !isOpen);

    if (isOpen) {
      unread = 0;
      updateBadge();
      if (!sid) {
        try { await apiInit(); renderAll(); } catch {}
      }
      startPoll();
      setTimeout(() => $input.focus(), 50);
    } else {
      stopPoll();
    }
  }

  // ── Send ────────────────────────────────────────────────────────────────────
  async function onSend() {
    const text = $input.value.trim();
    if (!text || busy) return;
    busy = true;
    $send.disabled = true;

    if (!sid) {
      try { await apiInit(); renderAll(); } catch { busy = false; $send.disabled = false; return; }
    }

    const localTs = Date.now() / 1e3;
    pendingUserTs.push(localTs);
    const msg = { ts: localTs, from: 'user', text };
    msgs.push(msg);
    appendMsg(msg);
    persist();

    $input.value = '';
    $input.style.height = 'auto';

    try { await apiSend(text); } catch {}
    busy = false;
    $send.disabled = !$input.value.trim();
  }

  // ── Upload ──────────────────────────────────────────────────────────────────
  async function onFileChange(e) {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    if (!sid) {
      try { await apiInit(); renderAll(); } catch { return; }
    }

    const localTs = Date.now() / 1e3;
    pendingUserTs.push(localTs);
    const local = URL.createObjectURL(file);
    const isPdf = file.type === 'application/pdf';
    const msg = isPdf
      ? { ts: localTs, from: 'user', file_url: local, file_name: file.name }
      : { ts: localTs, from: 'user', photo_url: local };
    msgs.push(msg);
    appendMsg(msg);
    persist();

    try { await apiUpload(file); } catch {}
  }

  // ── Boot ────────────────────────────────────────────────────────────────────
  function init() {
    injectCSS();
    if (sid) hydrate();
    buildUI();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
