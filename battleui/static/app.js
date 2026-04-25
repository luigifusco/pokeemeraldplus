// battleui client — landscape mobile, tap-to-fire.

const ACTION = { FIGHT: 0, SWITCH: 1, ITEM: 2, CANCEL_PARTNER: 3 };

const $ = (id) => document.getElementById(id);

const state = {
    ws: null,
    request: null,
    selectedMove: null,
    isDoubles: false,
    activeTab: "fight",
    names: { species: {}, moves: {} },
};

// ---- names ---------------------------------------------------------
function loadNames() {
    fetch("/names.json")
        .then(r => r.json())
        .then(n => {
            state.names = n || { species: {}, moves: {} };
            if (state.request) renderRequest();
        })
        .catch(() => {});
}
function speciesName(id) {
    return (state.names.species && state.names.species[id]) || ("#" + id);
}
function moveName(id) {
    return (state.names.moves && state.names.moves[id]) || ("Move " + id);
}
function spriteUrl(id) {
    const name = state.names.species && state.names.species[id];
    if (!name) return "";
    const slug = name.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!slug) return "";
    return `https://play.pokemonshowdown.com/sprites/gen3/${slug}.png`;
}

// ---- connection ----------------------------------------------------
function setStatus(cls, text) {
    const el = $("status");
    el.className = "status " + cls;
    el.textContent = text;
}

function connect() {
    const tok = new URLSearchParams(location.search).get("token") || "";
    const qs = tok ? `?token=${encodeURIComponent(tok)}` : "";
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${location.host}/ws${qs}`;
    setStatus("status-waiting", "connecting…");
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => setStatus("status-waiting", "waiting for emulator");
    ws.onclose = () => {
        setStatus("status-offline", "offline");
        state.ws = null;
        setTimeout(connect, 1000);
    };
    ws.onerror = () => {};
    ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch (_) { return; }
        onMessage(msg);
    };
}

function onMessage(msg) {
    if (msg.type === "request") {
        setStatus("status-connected", "decide");
        state.request = msg;
        renderRequest();
    } else if (msg.type === "heartbeat") {
        if (!state.request) setStatus("status-connected", "connected");
    } else if (msg.type === "hello") {
        state.request = null;
        renderIdle();
    }
}

function send(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(obj));
    }
}

function submit(action, param1, param2) {
    if (!state.request) return;
    send({ type: "response", seq: state.request.seq, action, param1: param1|0, param2: param2|0 });
    state.request = null;
    state.selectedMove = null;
    renderIdle();
    setStatus("status-connected", "connected");
}

// ---- helpers -------------------------------------------------------
function nicknameToString(n) {
    if (!n) return "";
    if (typeof n === "string") return n.replace(/\0.*$/, "").trim();
    if (!Array.isArray(n)) return "";
    const out = [];
    for (const b of n) {
        if (b === 0xFF || b === 0) break;
        if (b >= 0x20 && b <= 0x7E) out.push(String.fromCharCode(b));
    }
    return out.join("").trim();
}

function hpClass(hp, maxHp) {
    if (!maxHp) return "";
    const p = hp / maxHp;
    if (p <= 0.2) return "low";
    if (p <= 0.5) return "med";
    return "";
}

function monHTML(m, spriteCls) {
    if (!m || !m.maxHp) return '<div class="dash">—</div>';
    const pct = Math.max(0, Math.min(100, (m.hp / m.maxHp) * 100));
    const status = m.status1 ? '<span class="badge">STS</span>' : "";
    const sprite = spriteUrl(m.species);
    const cls = spriteCls || "mon-sprite";
    const spriteHTML = sprite
        ? `<img class="${cls}" src="${sprite}" alt="" onerror="this.style.display='none'">`
        : "";
    return `
        <div class="mon-with-sprite">
            ${spriteHTML}
            <div class="mon-body">
                <div class="mon-species">${speciesName(m.species)} Lv${m.level}${status}</div>
                <div class="mon-line"><span>${m.hp}/${m.maxHp}</span></div>
                <div class="hp-bar"><div class="hp-fill ${hpClass(m.hp, m.maxHp)}" style="width:${pct}%"></div></div>
            </div>
        </div>
    `;
}

function controlledMonsHTML(r) {
    const p = r.partyInfo || {};
    const partnerSlot = p.partnerMonId;
    const partnerMon = p.mons && partnerSlot < p.mons.length ? p.mons[partnerSlot] : null;
    const hasPartner = partnerMon && partnerMon.maxHp > 0;

    if (!hasPartner)
        return monHTML(r.controlledMon);

    return `
        <div class="controlled-pair">
            <div class="controlled-slot active">
                <div class="slot-label">ACTING</div>
                ${monHTML(r.controlledMon)}
            </div>
            <div class="controlled-slot">
                <div class="slot-label">PARTNER</div>
                ${monHTML(partnerMon)}
            </div>
        </div>
    `;
}

// ---- rendering -----------------------------------------------------
function renderIdle() {
    $("idle").classList.remove("hidden");
    ["fight","switch","item","cancel"].forEach(t => $("pane-"+t).classList.add("hidden"));
}

function showActivePane() {
    $("idle").classList.add("hidden");
    ["fight","switch","item","cancel"].forEach(t => {
        $("pane-"+t).classList.toggle("hidden", t !== state.activeTab);
    });
}

function renderRequest() {
    showActivePane();

    const r = state.request;
    $("controlledMon").innerHTML = controlledMonsHTML(r);
    $("targetLeft").innerHTML = monHTML(r.targetMonLeft);

    const hasRight = r.targetMonRight && r.targetMonRight.maxHp > 0 && r.targetBattlerRight !== r.targetBattlerLeft;
    state.isDoubles = hasRight;
    $("rightCard").classList.toggle("dim", !hasRight);
    $("targetRight").innerHTML = hasRight ? monHTML(r.targetMonRight) : '<div class="dash">—</div>';

    $("cancelTab").style.display = hasRight ? "" : "none";
    if (!hasRight && state.activeTab === "cancel") switchTab("fight");

    renderMoves();
    renderParty();
    renderItems();

    $("tpL").textContent = "slot " + r.targetBattlerLeft;
    $("tpR").textContent = "slot " + r.targetBattlerRight;
    $("targetPicker").classList.add("hidden");
}

function isActionStage(mi) {
    if (!mi || !mi.moves) return true;
    return mi.moves.every(m => !m);
}

function renderMoves() {
    const mi = state.request.moveInfo || { moves:[0,0,0,0], currentPp:[0,0,0,0], maxPp:[0,0,0,0] };
    const grid = $("moveGrid");
    grid.innerHTML = "";
    state.selectedMove = null;
    $("targetPicker").classList.add("hidden");

    const noMoves = isActionStage(mi);
    if (noMoves) {
        // Move list unavailable (e.g. forced move not yet revealed). Fall
        // back to a single FIGHT button — engine will pick move 0.
        const btn = document.createElement("button");
        btn.className = "move-btn action-fight";
        btn.innerHTML = `<div class="move-name">FIGHT</div>
                         <div class="move-pp">no move list — auto-pick</div>`;
        btn.onclick = () => submit(ACTION.FIGHT, 0, state.request.targetBattlerLeft);
        grid.appendChild(btn);
        return;
    }

    for (let i = 0; i < 4; i++) {
        const id = mi.moves[i];
        const cur = mi.currentPp[i], max = mi.maxPp[i];
        const btn = document.createElement("button");
        btn.className = "move-btn";
        btn.disabled = !id || cur === 0;
        btn.innerHTML = `<div class="move-name">${id ? moveName(id) : "—"}</div>
                         <div class="move-pp">PP ${cur}/${max}</div>`;
        btn.onclick = () => onMoveTap(i);
        grid.appendChild(btn);
    }
}

function onMoveTap(i) {
    const r = state.request;
    const mi = r.moveInfo;
    if (!mi.moves[i] || mi.currentPp[i] === 0) return;

    if (!state.isDoubles) {
        // Singles: fire immediately.
        submit(ACTION.FIGHT, i, r.targetBattlerLeft);
        return;
    }

    // Doubles: highlight & show target picker.
    state.selectedMove = i;
    Array.from($("moveGrid").children).forEach((el, idx) => {
        el.classList.toggle("selected", idx === i);
    });
    $("targetPicker").classList.remove("hidden");
}

function onTargetTap(side) {
    const r = state.request;
    if (!r || state.selectedMove === null) return;
    const tgt = side === "R" ? r.targetBattlerRight : r.targetBattlerLeft;
    submit(ACTION.FIGHT, state.selectedMove, tgt);
}

function renderParty() {
    const p = state.request.partyInfo;
    const list = $("partyList");
    list.innerHTML = "";
    for (let i = p.firstMonId; i < p.lastMonId; i++) {
        const mon = p.mons[i];
        if (!mon) continue;
        const isCurrent = (i === p.currentMonId) || (i === p.partnerMonId);
        const fainted = !mon.hp;
        const disabled = isCurrent || fainted || !mon.maxHp;
        const row = document.createElement("button");
        row.className = "party-row" + (disabled ? " disabled" : "");
        row.disabled = disabled;
        const status = mon.status1 ? '<span class="badge">STS</span>' : "";
        const pct = mon.maxHp ? Math.max(0, Math.min(100, (mon.hp/mon.maxHp)*100)) : 0;
        const sprite = spriteUrl(mon.species);
        const spriteHTML = sprite
            ? `<img class="party-sprite" src="${sprite}" alt="" onerror="this.style.display='none'">`
            : "";
        row.innerHTML = `
            ${spriteHTML}
            <div class="mon-species">${speciesName(mon.species)} Lv${mon.level}${status}</div>
            <div class="mon-line"><span>${mon.hp}/${mon.maxHp}${isCurrent?" • active":fainted?" • KO":""}</span></div>
            <div class="hp-bar"><div class="hp-fill ${hpClass(mon.hp, mon.maxHp)}" style="width:${pct}%"></div></div>
        `;
        row.onclick = () => { if (!disabled) submit(ACTION.SWITCH, i, 0); };
        list.appendChild(row);
    }
}

function renderItems() {
    const list = $("itemList");
    list.innerHTML = "";
    const items = state.request.trainerItems || [];
    let any = false;
    items.forEach((id, idx) => {
        if (!id) return;
        any = true;
        const btn = document.createElement("button");
        btn.className = "item-btn";
        btn.innerHTML = `<div class="mon-species">Item #${id}</div>
                         <div class="mon-line"><span>slot ${idx}</span></div>`;
        btn.onclick = () => submit(ACTION.ITEM, idx, 0);
        list.appendChild(btn);
    });
    if (!any) list.innerHTML = '<div class="idle-text" style="grid-column:1/-1">No trainer items.</div>';
}

// ---- tabs ---------------------------------------------------------
function switchTab(name) {
    state.activeTab = name;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    if (state.request) showActivePane();
}

document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));

document.addEventListener("click", (ev) => {
    const t = ev.target.closest(".target-btn");
    if (t) onTargetTap(t.dataset.t);
});

$("submitCancel").addEventListener("click", () => submit(ACTION.CANCEL_PARTNER, 0, 0));

renderIdle();
loadNames();
connect();
