(function () {
    "use strict";

    // ── Config ──────────────────────────────────────────────────────────────────
    const script = document.currentScript;
    const cfg = window.__SW || {};

    const API = (
        script?.dataset.api ||
        cfg.api ||
        (script?.src ? new URL(script.src).origin : "")
    ).replace(/\/$/, "");

    const USER_ID = script?.dataset.userId || cfg.userId || null;

    if (!API) {
        console.warn("[SW] data-api required");
        return;
    }
    if (!USER_ID) {
        console.warn("[SW] data-user-id required");
        return;
    }

    const USER_ID_VALUE = (() => {
        const n = Number(USER_ID);
        return Number.isFinite(n) && String(USER_ID).trim() !== ""
            ? n
            : USER_ID;
    })();

    const LAUNCHER = !(
        cfg.launcher === false || script?.dataset.launcher === "false"
    );

    const LANG =
        script?.dataset.lang ||
        cfg.lang ||
        document.documentElement.lang?.slice(0, 2) ||
        "ru";
    const I18N = {
        ru: {
            title: "Поддержка",
            hint: "Введите сообщение…",
            welcome: "Привет! Чем можем помочь?",
            attach: "Прикрепить файл",
            closed: "Чат закрыт.",
            newChat: "Открыть новый чат",
            download: "Скачать",
            openOriginal: "Открыть в новой вкладке",
            noPreview: "Предпросмотр недоступен",
            viewerClose: "Закрыть",
        },
        en: {
            title: "Support",
            hint: "Type a message…",
            welcome: "Hi! How can we help you?",
            attach: "Attach a file",
            closed: "This chat has been closed.",
            newChat: "Start new chat",
            download: "Download",
            openOriginal: "Open in a new tab",
            noPreview: "Preview is not available",
            viewerClose: "Close",
        },
    };
    const T = I18N[LANG] || I18N.ru;

    // ── Color utils ───────────────────────────────────────────────────────────────
    function _rgb(hex) {
        const h = String(hex).replace("#", "");
        const s =
            h.length === 3
                ? h
                      .split("")
                      .map((c) => c + c)
                      .join("")
                : h.slice(0, 6);
        const n = parseInt(s, 16);
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    function _hex(rgb) {
        return (
            "#" +
            rgb
                .map((c) =>
                    Math.min(255, Math.max(0, Math.round(c)))
                        .toString(16)
                        .padStart(2, "0"),
                )
                .join("")
        );
    }
    function _shade(hex, f) {
        // f > 0 → darken, f < 0 → lighten toward white
        return _hex(
            _rgb(hex).map((c) => (f > 0 ? c * (1 - f) : c + (255 - c) * -f)),
        );
    }
    function _mix(a, b, t) {
        // t = weight of b (0..1)
        const A = _rgb(a),
            B = _rgb(b);
        return _hex(A.map((c, i) => c + (B[i] - c) * t));
    }
    function _rgba(hex, a) {
        const [r, g, b] = _rgb(hex);
        return `rgba(${r},${g},${b},${a})`;
    }
    function _isValid(c) {
        return typeof c === "string" && /^#?[0-9a-fA-F]{3,8}$/.test(c.trim());
    }
    // Контрастный цвет текста для подложки: чёрный на светлом (напр. жёлтом)
    // акценте, белый — на тёмном.
    function _onColor(hex) {
        const [r, g, b] = _rgb(hex).map((c) => {
            const s = c / 255;
            return s <= 0.03928
                ? s / 12.92
                : Math.pow((s + 0.055) / 1.055, 2.4);
        });
        const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        return L > 0.55 ? "#111111" : "#ffffff";
    }
    function pick(key, dataKey, fallback) {
        const fromData = script?.dataset?.[dataKey];
        const fromCfg = cfg.theme?.[key] ?? cfg[key];
        const v = fromData ?? fromCfg;
        return _isValid(v) ? (v[0] === "#" ? v : "#" + v) : fallback;
    }

    function buildTheme() {
        const primary = pick(
            "primary",
            "colorPrimary",
            "#2563eb",
        ).toLowerCase();
        const surface = "#ffffff";
        const text = "#1e293b";

        return {
            primary,
            primaryDark: pick(
                "primaryDark",
                "colorPrimaryDark",
                _shade(primary, 0.15),
            ),
            primaryLight: pick(
                "primaryLight",
                "colorPrimaryLight",
                _rgba(primary, 0.1),
            ),
            primaryDisabled: _mix(primary, surface, 0.55),
            onPrimary: pick("onPrimary", "colorOnPrimary", _onColor(primary)),

            bg: "#ffffff",
            surface,
            text,
            bubbleIn: "#f1f5f9",
            textMuted: _rgba(text, 0.55),
            border: "#e2e8f0",
            inputBg: "#f8fafc",

            shadow1: _rgba(primary, 0.45),
            shadow2: _rgba(primary, 0.55),
            bubbleInShadow: "rgba(0,0,0,.06)",
            winShadow: "rgba(0,0,0,.18)",
        };
    }

    const TH = buildTheme();

    // ── State ───────────────────────────────────────────────────────────────────
    const SID_KEY = "sw:sid:" + USER_ID;
    let sid = localStorage.getItem(SID_KEY) || null;
    let msgs = []; // [{ts, from:'bot'|'user'|'support', text?, photo_url?, file_url?, file_name?}]
    let offset = 0; // how many messages already fetched
    let isOpen = false;
    let busy = false;
    let unread = 0;
    let pollId = null;
    // Timestamps of user messages shown locally this session — used to skip duplicates from poll
    const pendingUserTs = [];

    const mk = (k) => `sw:${k}:${sid}`;

    function persist() {
        if (!sid) return;
        try {
            localStorage.setItem(mk("m"), JSON.stringify(msgs));
            localStorage.setItem(mk("o"), String(offset));
        } catch {}
    }

    function hydrate() {
        if (!sid) return;
        try {
            msgs = JSON.parse(localStorage.getItem(mk("m")) || "[]");
        } catch {
            msgs = [];
        }
        offset = +(localStorage.getItem(mk("o")) || 0);
    }

    // ── API helpers ─────────────────────────────────────────────────────────────
    function authHdrs(extra = {}) {
        const h = { ...extra };
        if (sid) h["X-Session-Id"] = sid;
        return h;
    }

    async function apiInit() {
        const body = { user_id: USER_ID_VALUE };
        const r = await fetch(API + "/widget/session", {
            method: "POST",
            headers: authHdrs({ "Content-Type": "application/json" }),
            body: JSON.stringify(body),
        });
        const d = await r.json();
        if (!d.session_id) throw new Error("session error");
        sid = d.session_id;
        localStorage.setItem(SID_KEY, sid);
        hydrate();
        if (!msgs.length) {
            msgs.push({ ts: Date.now() / 1e3, from: "bot", text: T.welcome });
            persist();
        }
    }

    async function apiSend(text) {
        const r = await fetch(API + "/widget/message", {
            method: "POST",
            headers: authHdrs({ "Content-Type": "application/json" }),
            body: JSON.stringify({ text }),
        });
        return (await r.json()).ok;
    }

    async function apiUpload(file) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(API + "/widget/upload", {
            method: "POST",
            headers: authHdrs(),
            body: fd,
        });
        return (await r.json()).ok;
    }

    async function apiPoll() {
        const r = await fetch(`${API}/widget/messages?offset=${offset}`, {
            headers: authHdrs(),
        });
        if (r.status === 401) {
            const e = new Error("401");
            e.status = 401;
            throw e;
        }
        return await r.json();
    }

    // ── CSS ─────────────────────────────────────────────────────────────────────
    function injectCSS() {
        if (document.getElementById("sw-css")) return;
        const el = document.createElement("style");
        el.id = "sw-css";
        // Theme tokens live on the two top-level nodes; everything inside inherits them.
        el.textContent = `
#sw-btn,#sw-win{
  --sw-primary:${TH.primary};
  --sw-primary-dark:${TH.primaryDark};
  --sw-primary-light:${TH.primaryLight};
  --sw-primary-disabled:${TH.primaryDisabled};
  --sw-on-primary:${TH.onPrimary};
  --sw-bg:${TH.bg};
  --sw-surface:${TH.surface};
  --sw-bubble-in:${TH.bubbleIn};
  --sw-text:${TH.text};
  --sw-text-muted:${TH.textMuted};
  --sw-border:${TH.border};
  --sw-input-bg:${TH.inputBg};
  --sw-shadow-1:${TH.shadow1};
  --sw-shadow-2:${TH.shadow2};
  --sw-bubble-in-shadow:${TH.bubbleInShadow};
  --sw-win-shadow:${TH.winShadow};
}
#sw-btn{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;
  background:var(--sw-primary);color:var(--sw-on-primary);border:none;cursor:pointer;
  box-shadow:0 4px 20px var(--sw-shadow-1);display:flex;align-items:center;
  justify-content:center;z-index:99998;transition:transform .2s,box-shadow .2s;}
#sw-btn:hover{transform:scale(1.08);box-shadow:0 6px 24px var(--sw-shadow-2);}
#sw-badge{position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;padding:0 4px;
  border-radius:9px;background:#ef4444;color:#fff;font:700 10px/18px system-ui;
  display:none;align-items:center;justify-content:center;border:2px solid var(--sw-surface);box-sizing:border-box;}
#sw-win{position:fixed;bottom:92px;right:24px;width:360px;height:520px;background:var(--sw-surface);
  border-radius:16px;box-shadow:0 8px 40px var(--sw-win-shadow);display:flex;flex-direction:column;
  overflow:hidden;z-index:99999;transform-origin:bottom right;
  transition:transform .2s cubic-bezier(.34,1.56,.64,1),opacity .15s;}
#sw-win.sw-hide{transform:scale(.88);opacity:0;pointer-events:none;}
.sw-head{background:var(--sw-primary);color:var(--sw-on-primary);padding:14px 16px;display:flex;align-items:center;
  gap:8px;flex-shrink:0;font:600 15px/1 system-ui;}
.sw-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;flex-shrink:0;}
.sw-head-title{flex:1;}
.sw-close{background:none;border:none;color:var(--sw-on-primary);opacity:.75;cursor:pointer;
  font-size:22px;line-height:1;padding:0;display:flex;align-items:center;transition:opacity .15s;}
.sw-close:hover{opacity:1;}
.sw-body{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;
  gap:6px;background:var(--sw-bg);scroll-behavior:smooth;}
.sw-body::-webkit-scrollbar{width:4px;}
.sw-body::-webkit-scrollbar-thumb{background:var(--sw-text-muted);border-radius:2px;}
.sw-bubble{max-width:82%;padding:9px 13px;border-radius:16px;font:14px/1.45 system-ui;
  word-break:break-word;animation:sw-in .2s ease;}
@keyframes sw-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.sw-bubble.sw-out{align-self:flex-end;background:var(--sw-primary);color:var(--sw-on-primary);border-bottom-right-radius:4px;}
.sw-bubble.sw-in {align-self:flex-start;background:var(--sw-bubble-in);color:var(--sw-text);
  border-bottom-left-radius:4px;box-shadow:0 1px 4px var(--sw-bubble-in-shadow);}
.sw-bubble img,.sw-bubble .sw-media{max-width:100%;border-radius:8px;display:block;cursor:zoom-in;margin-top:4px;transition:filter .15s;}
.sw-bubble .sw-media:hover{filter:brightness(.94);}
.sw-bubble .sw-file{display:flex;align-items:center;gap:8px;width:100%;max-width:240px;margin-top:4px;
  padding:8px 10px;border:none;border-radius:10px;cursor:pointer;text-align:left;
  background:rgba(0,0,0,.06);color:inherit;font:inherit;transition:filter .15s;}
.sw-bubble.sw-out .sw-file{background:rgba(255,255,255,.18);}
.sw-bubble .sw-file:hover{filter:brightness(.95);}
.sw-file-ico{flex-shrink:0;display:flex;opacity:.85;}
.sw-file-name{font-size:13px;line-height:1.3;word-break:break-all;overflow:hidden;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}
.sw-bubble a{color:inherit;text-decoration:underline;word-break:break-all;}
.sw-bubble .sw-fname{font-size:12px;opacity:.7;margin-top:2px;}
.sw-bubble .sw-time{font-size:11px;opacity:.5;margin-top:3px;text-align:right;}
.sw-foot{padding:10px 10px 12px;border-top:1px solid var(--sw-border);display:flex;
  gap:6px;align-items:flex-end;background:var(--sw-surface);flex-shrink:0;}
#sw-input{flex:1;border:1.5px solid var(--sw-border);border-radius:20px;padding:9px 14px;
  font:14px/1.4 system-ui;resize:none;outline:none;max-height:96px;overflow-y:auto;
  background:var(--sw-input-bg);color:var(--sw-text);transition:border .15s;}
#sw-input::placeholder{color:var(--sw-text-muted);}
#sw-input:focus{border-color:var(--sw-primary);}
.sw-icon-btn{width:36px;height:36px;border:none;background:none;cursor:pointer;
  color:var(--sw-text-muted);display:flex;align-items:center;justify-content:center;
  border-radius:50%;flex-shrink:0;transition:background .15s,color .15s;}
.sw-icon-btn:hover{background:var(--sw-primary-light);color:var(--sw-primary);}
#sw-send{background:var(--sw-primary);color:var(--sw-on-primary);transition:background .15s;}
#sw-send:hover{background:var(--sw-primary-dark);color:var(--sw-on-primary);}
#sw-send:disabled{background:var(--sw-primary-disabled);cursor:default;}
.sw-closed-notice{align-self:center;text-align:center;display:flex;flex-direction:column;gap:8px;align-items:center;}
.sw-new-chat-btn{margin-top:4px;padding:7px 16px;border-radius:20px;border:none;cursor:pointer;
  background:var(--sw-primary);color:var(--sw-on-primary);font:600 13px/1 system-ui;transition:background .15s;}
.sw-new-chat-btn:hover{background:var(--sw-primary-dark);}
#sw-viewer{position:fixed;inset:0;z-index:100000;display:flex;flex-direction:column;
  background:rgba(15,23,42,.92);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);
  opacity:1;transition:opacity .18s;font-family:system-ui;}
#sw-viewer.sw-vhide{opacity:0;pointer-events:none;}
.sw-viewer-bar{display:flex;align-items:center;gap:10px;padding:12px 16px;color:#fff;flex-shrink:0;}
.sw-viewer-name{flex:1;font:600 14px/1.3 system-ui;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;opacity:.92;}
.sw-viewer-acts{display:flex;gap:6px;align-items:center;}
.sw-viewer-act{width:38px;height:38px;border-radius:50%;border:none;cursor:pointer;
  display:flex;align-items:center;justify-content:center;color:#fff;background:rgba(255,255,255,.12);
  text-decoration:none;transition:background .15s;}
.sw-viewer-act:hover{background:rgba(255,255,255,.24);}
.sw-viewer-stage{flex:1;display:flex;align-items:center;justify-content:center;
  overflow:auto;padding:0 16px 20px;min-height:0;}
.sw-viewer-img{max-width:100%;max-height:100%;object-fit:contain;border-radius:8px;
  cursor:zoom-in;box-shadow:0 8px 40px rgba(0,0,0,.5);}
.sw-viewer-img.sw-zoomed{max-width:none;max-height:none;cursor:zoom-out;}
.sw-viewer-frame{width:100%;height:100%;border:none;border-radius:8px;background:#fff;}
.sw-viewer-fallback{display:flex;flex-direction:column;align-items:center;gap:10px;color:#fff;text-align:center;}
.sw-viewer-fileico{width:64px;height:64px;display:flex;align-items:center;justify-content:center;
  border-radius:16px;background:rgba(255,255,255,.12);}
.sw-viewer-fileico svg{width:32px;height:32px;}
.sw-viewer-fname{font:600 15px/1.3 system-ui;word-break:break-all;max-width:80vw;}
.sw-viewer-nopreview{font:13px/1.4 system-ui;opacity:.7;}
@media(max-width:420px){
  #sw-win{left:12px;right:12px;width:auto;height:min(72dvh,560px);
    bottom:12px;border-radius:16px;}
  #sw-btn{bottom:16px;right:16px;}
}`;
        document.head.appendChild(el);
    }

    // ── DOM builders ────────────────────────────────────────────────────────────
    let $body, $input, $send, $badge, $win;
    let $viewer, $vStage, $vName, $vDownload, $vExternal;

    function svgChat() {
        return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
    }
    function svgSend() {
        return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
    }
    function svgAttach() {
        return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`;
    }
    function svgFile() {
        return `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
    }
    function svgPdf() {
        return `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15h1.5a1.5 1.5 0 0 0 0-3H9v5"/><path d="M14 13h2"/><path d="M15 12v5"/></svg>`;
    }
    function svgDownload() {
        return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
    }
    function svgExternal() {
        return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
    }
    function svgX() {
        return `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    }

    function buildViewer() {
        if ($viewer) return;
        $viewer = document.createElement("div");
        $viewer.id = "sw-viewer";
        $viewer.className = "sw-vhide";
        $viewer.innerHTML = `
      <div class="sw-viewer-bar">
        <span class="sw-viewer-name"></span>
        <div class="sw-viewer-acts">
          <a class="sw-viewer-act" id="sw-viewer-dl" target="_blank" rel="noopener" title="${T.download}" aria-label="${T.download}">${svgDownload()}</a>
          <a class="sw-viewer-act" id="sw-viewer-ext" target="_blank" rel="noopener" title="${T.openOriginal}" aria-label="${T.openOriginal}">${svgExternal()}</a>
          <button type="button" class="sw-viewer-act" id="sw-viewer-x" title="${T.viewerClose}" aria-label="${T.viewerClose}">${svgX()}</button>
        </div>
      </div>
      <div class="sw-viewer-stage"></div>`;
        document.body.appendChild($viewer);

        $vStage = $viewer.querySelector(".sw-viewer-stage");
        $vName = $viewer.querySelector(".sw-viewer-name");
        $vDownload = $viewer.querySelector("#sw-viewer-dl");
        $vExternal = $viewer.querySelector("#sw-viewer-ext");
        $viewer
            .querySelector("#sw-viewer-x")
            .addEventListener("click", closeViewer);
        // Клик по тёмному фону (мимо контента и панели) — закрыть.
        $viewer.addEventListener("click", (e) => {
            if (e.target === $viewer || e.target === $vStage) closeViewer();
        });
    }

    function onViewerKey(e) {
        if (e.key === "Escape") closeViewer();
    }

    function openViewer(type, url, name) {
        buildViewer();
        $vName.textContent = name || "";
        $vDownload.href = url;
        if (name) $vDownload.setAttribute("download", name);
        else $vDownload.removeAttribute("download");
        $vExternal.href = url;

        const safeUrl = escHtml(url);
        const safeName = escHtml(name || "");
        if (type === "image") {
            $vStage.innerHTML = `<img class="sw-viewer-img" src="${safeUrl}" alt="${safeName}">`;
            const img = $vStage.querySelector(".sw-viewer-img");
            img.addEventListener("click", (e) => {
                e.stopPropagation();
                img.classList.toggle("sw-zoomed");
            });
        } else if (type === "pdf") {
            $vStage.innerHTML = `<iframe class="sw-viewer-frame" src="${safeUrl}" title="${safeName || "PDF"}"></iframe>`;
        } else {
            $vStage.innerHTML = `<div class="sw-viewer-fallback">
              <div class="sw-viewer-fileico">${svgFile()}</div>
              <div class="sw-viewer-fname">${safeName}</div>
              <div class="sw-viewer-nopreview">${T.noPreview}</div>
            </div>`;
        }

        $viewer.classList.remove("sw-vhide");
        document.addEventListener("keydown", onViewerKey);
    }

    function closeViewer() {
        if (!$viewer) return;
        $viewer.classList.add("sw-vhide");
        $vStage.innerHTML = ""; // освобождаем iframe/изображение
        document.removeEventListener("keydown", onViewerKey);
    }

    function onAttachClick(e) {
        const t = e.target.closest("[data-sw-view]");
        if (!t) return;
        e.preventDefault();
        openViewer(t.dataset.swType, t.dataset.swUrl, t.dataset.swName || "");
    }

    function buildUI() {
        if (LAUNCHER) {
            const btn = document.createElement("button");
            btn.id = "sw-btn";
            btn.setAttribute("aria-label", T.title);
            btn.innerHTML = svgChat();
            $badge = document.createElement("span");
            $badge.id = "sw-badge";
            btn.appendChild($badge);
            btn.addEventListener("click", requestToggle);
            document.body.appendChild(btn);
        }

        // Window
        $win = document.createElement("div");
        $win.id = "sw-win";
        $win.classList.add("sw-hide");
        $win.innerHTML = `
      <div class="sw-head">
        <span class="sw-dot"></span>
        <span class="sw-head-title">${T.title}</span>
        <button class="sw-close" aria-label="Close">&#x2715;</button>
      </div>
      <div class="sw-body"></div>
      <div class="sw-foot">
        <button class="sw-icon-btn" id="sw-attach" title="${T.attach}">${svgAttach()}</button>
        <input type="file" id="sw-file" accept="image/*,application/pdf" style="display:none">
        <textarea id="sw-input" rows="1" placeholder="${T.hint}"></textarea>
        <button class="sw-icon-btn" id="sw-send" disabled>${svgSend()}</button>
      </div>`;

        $win.querySelector(".sw-close").addEventListener("click", toggle);

        document.body.appendChild($win);

        $body = $win.querySelector(".sw-body");
        $body.addEventListener("click", onAttachClick);
        $input = $win.querySelector("#sw-input");
        $send = $win.querySelector("#sw-send");
        const $attach = $win.querySelector("#sw-attach");
        const $file = $win.querySelector("#sw-file");

        $attach.addEventListener("click", () => $file.click());
        $file.addEventListener("change", onFileChange);

        $input.addEventListener("input", () => {
            $input.style.height = "auto";
            $input.style.height = Math.min($input.scrollHeight, 96) + "px";
            $send.disabled = !$input.value.trim();
        });
        $input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
            }
        });
        $send.addEventListener("click", onSend);

        renderAll();
    }

    // ── Rendering ───────────────────────────────────────────────────────────────
    function fmtTime(ts) {
        const d = new Date(ts * 1000);
        return (
            d.getHours().toString().padStart(2, "0") +
            ":" +
            d.getMinutes().toString().padStart(2, "0")
        );
    }

    function absUrl(url) {
        if (!url) return url;
        return url.startsWith("/") ? API + url : url;
    }

    function fileNameFromUrl(url) {
        return url.split("?")[0].split("/").pop() || "file";
    }
    function viewKind(url) {
        const ext = url.split("?")[0].split(".").pop().toLowerCase();
        if (/^(jpg|jpeg|png|gif|webp|bmp|svg)$/.test(ext)) return "image";
        if (ext === "pdf") return "pdf";
        return "file";
    }
    function attachHtml(url, name, forceKind) {
        const kind = forceKind || viewKind(url);
        const safeUrl = escHtml(url);
        const safeName = escHtml(name);
        if (kind === "image") {
            return `<img class="sw-media" src="${safeUrl}" alt="${safeName}" loading="lazy"
                data-sw-view data-sw-type="image" data-sw-url="${safeUrl}" data-sw-name="${safeName}">`;
        }
        const ico = kind === "pdf" ? svgPdf() : svgFile();
        return `<button type="button" class="sw-file"
                data-sw-view data-sw-type="${kind}" data-sw-url="${safeUrl}" data-sw-name="${safeName}">
              <span class="sw-file-ico">${ico}</span>
              <span class="sw-file-name">${safeName}</span>
            </button>`;
    }

    function makeBubble(msg) {
        const el = document.createElement("div");
        const out = msg.from === "user";
        el.className = "sw-bubble " + (out ? "sw-out" : "sw-in");
        el.dataset.ts = msg.ts;
        let html = "";
        if (msg.photo_url) {
            const url = absUrl(msg.photo_url);
            // photo_url — всегда изображение (в т.ч. локальный blob: без расширения).
            html += attachHtml(
                url,
                msg.file_name || fileNameFromUrl(url),
                "image",
            );
        }
        if (msg.file_url) {
            const url = absUrl(msg.file_url);
            html += attachHtml(url, msg.file_name || fileNameFromUrl(url));
        }
        if (msg.text) {
            html +=
                (html ? "<br>" : "") + escHtml(msg.text).replace(/\n/g, "<br>");
        }
        html += `<div class="sw-time">${fmtTime(msg.ts)}</div>`;
        el.innerHTML = html;
        return el;
    }

    function escHtml(s) {
        return s
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function renderAll() {
        if (!$body) return;
        $body.innerHTML = "";
        msgs.forEach((m) => $body.appendChild(makeBubble(m)));
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
            const serverTotal = typeof d.total === "number" ? d.total : null;

            let added = 0;
            newMsgs.forEach((m) => {
                if (m.from === "user") {
                    const ptIdx = pendingUserTs.findIndex(
                        (t) => Math.abs(t - m.ts) <= 3,
                    );
                    if (ptIdx !== -1) {
                        pendingUserTs.splice(ptIdx, 1);
                        // Replace blob URL with real server URL in msgs[] and DOM
                        const msgIdx = msgs.findIndex(
                            (lm) => lm.from === "user" && Math.abs(lm.ts - m.ts) <= 3,
                        );
                        if (msgIdx !== -1) {
                            const lm = msgs[msgIdx];
                            const needsUpdate =
                                lm.photo_url?.startsWith("blob:") ||
                                lm.file_url?.startsWith("blob:");
                            if (needsUpdate) {
                                if (lm.photo_url?.startsWith("blob:") && m.photo_url) lm.photo_url = m.photo_url;
                                if (lm.file_url?.startsWith("blob:") && m.file_url) lm.file_url = m.file_url;
                                if (m.file_name) lm.file_name = m.file_name;
                                persist();
                                const el = $body?.querySelector(`[data-ts="${lm.ts}"]`);
                                if (el) el.replaceWith(makeBubble(lm));
                            }
                        }
                        return;
                    }
                }
                msgs.push(m);
                appendMsg(msgs[msgs.length - 1]);
                if (m.from !== "user") unread++;
                added++;
            });

            if (serverTotal !== null) offset = serverTotal;
            else offset += newMsgs.length;

            if (added > 0 || serverTotal !== null) persist();
            updateBadge();
        } catch (err) {
            if (err?.status === 401) handleSessionClosed();
        }
    }

    function startPoll() {
        if (!pollId) pollId = setInterval(poll, 3000);
    }
    function stopPoll() {
        clearInterval(pollId);
        pollId = null;
    }

    function updateBadge() {
        if (!$badge) return;
        $badge.style.display = unread > 0 ? "flex" : "none";
        $badge.textContent = unread > 9 ? "9+" : String(unread);
    }

    function handleSessionClosed() {
        stopPoll();
        const oldSid = sid;
        sid = null;
        msgs = [];
        offset = 0;
        if (oldSid) {
            try {
                localStorage.removeItem(SID_KEY);
            } catch {}
            try {
                localStorage.removeItem(`sw:m:${oldSid}`);
            } catch {}
            try {
                localStorage.removeItem(`sw:o:${oldSid}`);
            } catch {}
        }
        if ($body) {
            $body.innerHTML = "";
            const el = document.createElement("div");
            el.className = "sw-bubble sw-in sw-closed-notice";
            el.innerHTML = `<span>${escHtml(T.closed)}</span>
                <button class="sw-new-chat-btn">${escHtml(T.newChat)}</button>`;
            el.querySelector(".sw-new-chat-btn").addEventListener(
                "click",
                onNewChat,
            );
            $body.appendChild(el);
            scrollBottom();
        }
        if ($input) $input.disabled = true;
        if ($send) $send.disabled = true;
    }

    async function onNewChat() {
        try {
            await apiInit();
        } catch {
            return;
        }
        if ($input) $input.disabled = false;
        renderAll();
        startPoll();
        setTimeout(() => $input?.focus(), 50);
    }

    // ── Toggle ──────────────────────────────────────────────────────────────────
    async function toggle() {
        isOpen = !isOpen;
        $win.classList.toggle("sw-hide", !isOpen);

        if (isOpen) {
            unread = 0;
            updateBadge();
            if (!sid) {
                try {
                    await apiInit();
                    renderAll();
                } catch {}
            }
            startPoll();
            setTimeout(() => $input.focus(), 50);
        } else {
            stopPoll();
        }
    }

    function requestToggle() {
        if (isOpen) {
            toggle();
            return;
        }
        const guard = window.__SW?.onBeforeOpen;
        if (typeof guard === "function") {
            guard(() => {
                if (!isOpen) toggle();
            });
        } else {
            toggle();
        }
    }

    // ── Send ────────────────────────────────────────────────────────────────────
    async function onSend() {
        const text = $input.value.trim();
        if (!text || busy) return;
        busy = true;
        $send.disabled = true;

        if (!sid) {
            try {
                await apiInit();
                renderAll();
            } catch {
                busy = false;
                $send.disabled = false;
                return;
            }
        }

        const localTs = Date.now() / 1e3;
        pendingUserTs.push(localTs);
        const msg = { ts: localTs, from: "user", text };
        msgs.push(msg);
        appendMsg(msg);
        persist();

        $input.value = "";
        $input.style.height = "auto";

        try {
            await apiSend(text);
        } catch {}
        busy = false;
        $send.disabled = !$input.value.trim();
    }

    // ── Upload ──────────────────────────────────────────────────────────────────
    async function onFileChange(e) {
        const file = e.target.files[0];
        e.target.value = "";
        if (!file) return;

        if (!sid) {
            try {
                await apiInit();
                renderAll();
            } catch {
                return;
            }
        }

        const localTs = Date.now() / 1e3;
        pendingUserTs.push(localTs);
        const local = URL.createObjectURL(file);
        const isImage = file.type.startsWith("image/");
        const msg = isImage
            ? { ts: localTs, from: "user", photo_url: local }
            : {
                  ts: localTs,
                  from: "user",
                  file_url: local,
                  file_name: file.name,
              };
        msgs.push(msg);
        appendMsg(msg);
        persist();

        try {
            await apiUpload(file);
        } catch {}
    }

    // ── Public API ────────────────────────────────────────────────────────────────
    function destroy() {
        stopPoll();
        document.removeEventListener("keydown", onViewerKey);
        document.getElementById("sw-btn")?.remove();
        document.getElementById("sw-css")?.remove();
        $win?.remove();
        $viewer?.remove();
        $viewer = null;
        try {
            delete window.SupportChat;
        } catch {}
    }

    // ── Boot ────────────────────────────────────────────────────────────────────
    function init() {
        injectCSS();
        if (sid) hydrate();
        buildUI();

        // Управление чатом извне (например, по клику на свою кнопку поддержки).
        window.SupportChat = {
            open() {
                if (!isOpen) toggle();
            },
            close() {
                if (isOpen) toggle();
            },
            toggle,
            destroy,
        };
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();