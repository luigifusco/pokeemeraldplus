// pokeemeraldplus randomizer - frontend
// No framework, plain ES2020. Modules: router, log, api.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------- Router (left-nav -> panel) ----------
const navItems = $$(".nav-item");
const panels = $$(".panel");
const title = $("#section-title");

function showSection(name) {
    navItems.forEach(b => b.classList.toggle("active", b.dataset.section === name));
    panels.forEach(p => p.classList.toggle("hidden", p.dataset.section !== name));
    const active = navItems.find(b => b.dataset.section === name);
    if (active) title.textContent = active.textContent.trim();
    try { history.replaceState(null, "", "#" + name); } catch (_) {}
}
navItems.forEach(b => b.addEventListener("click", () => showSection(b.dataset.section)));
const initial = (location.hash || "#randomizer").slice(1);
showSection(navItems.some(b => b.dataset.section === initial) ? initial : "randomizer");

// ---------- Health probe ----------
const healthPill = $("#health-pill");
const healthText = $("#health-text");
(async () => {
    try {
        const r = await fetch("/api/health");
        if (!r.ok) throw new Error(r.status);
        const j = await r.json();
        healthPill.classList.add("ok");
        healthText.textContent = "connected";
        healthPill.title = j.repo || "";
    } catch (e) {
        healthPill.classList.add("err");
        healthText.textContent = "offline";
    }
})();

// ---------- Log drawer ----------
const drawer = $("#log-drawer");
const logBody = $("#log-body");
const logStatus = $("#log-status");
const logLed = $("#log-led");

$("#log-toggle").addEventListener("click", () => drawer.classList.toggle("collapsed"));
$("#log-close").addEventListener("click", () => drawer.classList.add("collapsed"));
$("#log-clear").addEventListener("click", () => { logBody.innerHTML = ""; });
$("#log-copy").addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText(logBody.innerText);
    } catch (_) {}
});

// ANSI SGR -> span classes. Supports fg 30-37 / 90-97, bold 1/22, reset 0/39.
const ANSI_RE = /\x1b\[([0-9;]*)m/g;
function ansiToHtml(raw) {
    let html = "";
    let last = 0;
    let fg = null;
    let bold = false;
    const open = () => {
        const cls = [];
        if (fg !== null) cls.push("ansi-" + fg);
        if (bold) cls.push("ansi-bold");
        return cls.length ? `<span class="${cls.join(" ")}">` : "";
    };
    const close = () => (fg !== null || bold) ? "</span>" : "";
    let spanOpen = false;
    const flushOpen = () => {
        if (spanOpen) { html += close(); spanOpen = false; }
        const o = open();
        if (o) { html += o; spanOpen = true; }
    };
    const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    raw.replace(ANSI_RE, (match, codes, offset) => {
        html += escape(raw.slice(last, offset));
        last = offset + match.length;
        const parts = codes.split(";").filter(Boolean);
        if (parts.length === 0) { fg = null; bold = false; }
        for (const p of parts) {
            const n = parseInt(p, 10);
            if (n === 0) { fg = null; bold = false; }
            else if (n === 1) bold = true;
            else if (n === 22) bold = false;
            else if (n === 39) fg = null;
            else if ((n >= 30 && n <= 37) || (n >= 90 && n <= 97)) fg = n;
        }
        flushOpen();
    });
    html += escape(raw.slice(last));
    if (spanOpen) html += close();
    return html;
}

const LINE_CAP = 20000;
function appendLine(text, kind) {
    const div = document.createElement("div");
    div.className = "line" + (kind ? " " + kind : "");
    div.innerHTML = ansiToHtml(text);
    logBody.appendChild(div);
    while (logBody.childElementCount > LINE_CAP) logBody.removeChild(logBody.firstChild);
    // Follow-tail unless user has scrolled up.
    const atBottom = logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight < 40;
    if (atBottom) logBody.scrollTop = logBody.scrollHeight;
}

function setLogStatus(state, label) {
    logLed.classList.remove("running", "ok", "err");
    if (state) logLed.classList.add(state);
    logStatus.textContent = label;
}

// ---------- Public API (used by later phase scripts) ----------
window.randomizerUI = {
    showSection,
    log: {
        line: appendLine,
        info:    (t) => appendLine(t, "info"),
        success: (t) => appendLine(t, "success"),
        warn:    (t) => appendLine(t, "warn"),
        error:   (t) => appendLine(t, "error"),
        clear:   () => { logBody.innerHTML = ""; },
        setStatus: setLogStatus,
        open:    () => drawer.classList.remove("collapsed"),
    },
    api: {
        async preview(body) {
            const r = await fetch("/api/preview", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!r.ok) throw new Error(await r.text());
            return r.json();
        },
        async build(body) {
            const r = await fetch("/api/build", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!r.ok) throw new Error(await r.text());
            return r.json();
        },
        async stop(runId) {
            await fetch(`/api/runs/${runId}/stop`, { method: "POST" });
        },
        stream(runId, { onLine, onStep, onDone, onError }) {
            const es = new EventSource(`/api/runs/${runId}/events`);
            es.addEventListener("line", (e) => onLine && onLine(JSON.parse(e.data)));
            es.addEventListener("step", (e) => onStep && onStep(JSON.parse(e.data)));
            es.addEventListener("step_done", (e) => onStep && onStep({ ...JSON.parse(e.data), done: true }));
            es.addEventListener("error", (e) => {
                if (e.data) { try { onError && onError(JSON.parse(e.data)); } catch (_) {} }
            });
            es.addEventListener("done", (e) => {
                onDone && onDone(JSON.parse(e.data));
                es.close();
            });
            return es;
        },
    },
};
