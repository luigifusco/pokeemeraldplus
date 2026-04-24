// battleui client: WebSocket + DOM rendering.

const ACTION = { FIGHT: 0, SWITCH: 1, ITEM: 2, CANCEL_PARTNER: 3 };

const $ = (id) => document.getElementById(id);

const state = {
    ws: null,
    request: null,
    selectedMove: null,
    selectedTarget: null, // 'L' | 'R' | null
    isDoubles: false,
    activeTab: "fight",
};

// ---- connection ----------------------------------------------------
function setStatus(cls, text) {
    const el = $("status");
    el.className = "status " + cls;
    el.textContent = text;
}

function connect() {
    const url = `ws://${location.host}/ws`;
    setStatus("status-waiting", "connecting…");
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => setStatus("status-waiting", "waiting for emulator");
    ws.onclose = () => {
        setStatus("status-offline", "server offline");
        state.ws = null;
        setTimeout(connect, 1000);
    };
    ws.onerror = () => { /* onclose will retry */ };
    ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch (_) { return; }
        onMessage(msg);
    };
}

function onMessage(msg) {
    if (msg.type === "request") {
        setStatus("status-connected", "request pending");
        state.request = msg;
        renderRequest();
    } else if (msg.type === "heartbeat") {
        if (!state.request) setStatus("status-connected", "emulator connected");
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
    state.selectedTarget = null;
    renderIdle();
    setStatus("status-connected", "emulator connected");
}

// ---- rendering -----------------------------------------------------
function hpClass(hp, maxHp) {
    if (!maxHp) return "";
    const p = hp / maxHp;
    if (p <= 0.2) return "low";
    if (p <= 0.5) return "med";
    return "";
}

function monHTML(m) {
    if (!m || !m.maxHp) return '<div class="mon-species">—</div>';
    const pct = Math.max(0, Math.min(100, (m.hp / m.maxHp) * 100));
    const nick = (m.nickname || "").replace(/\0.*$/, "").trim();
    const status = m.status1 ? '<span class="badge">STS</span>' : "";
    return `
        <div class="mon-species">#${m.species} Lv${m.level}${status}</div>
        <div class="mon-line"><span>${nick || "(no name)"}</span><span>${m.hp}/${m.maxHp}</span></div>
        <div class="hp-bar"><div class="hp-fill ${hpClass(m.hp, m.maxHp)}" style="width:${pct}%"></div></div>
    `;
}

function renderIdle() {
    $("idle").classList.remove("hidden");
    $("request").classList.add("hidden");
}

function renderRequest() {
    $("idle").classList.add("hidden");
    $("request").classList.remove("hidden");

    const r = state.request;
    $("battlerId").textContent = r.battlerId;
    $("seq").textContent = r.seq;

    // mons
    const ctrl = r.controlledMon;
    $("controlledMon").innerHTML = monHTML(ctrl) +
        `<div>${typeChips(r.moveInfo && r.moveInfo.monTypes)}</div>`;
    $("targetLeft").innerHTML = monHTML(r.targetMonLeft);
    const hasRight = r.targetMonRight && r.targetMonRight.maxHp > 0 && r.targetBattlerRight !== r.targetBattlerLeft;
    state.isDoubles = hasRight;
    if (hasRight) {
        $("targetRightBox").classList.remove("hidden");
        $("targetRight").innerHTML = monHTML(r.targetMonRight);
    } else {
        $("targetRightBox").classList.add("hidden");
    }

    $("cancelTab").style.display = hasRight ? "" : "none";
    if (!hasRight && state.activeTab === "cancel") switchTab("fight");

    renderMoves();
    renderParty();
    renderItems();

    $("tpL").textContent = "slot " + r.targetBattlerLeft;
    $("tpR").textContent = "slot " + r.targetBattlerRight;
    $("targetPicker").classList.toggle("hidden", !hasRight);
}

function typeChips(types) {
    if (!types) return "";
    return types.filter((t, i, a) => t !== 0 || i === 0 || t !== a[0])
        .map((t) => `<span class="type-chip">type ${t}</span>`).join("");
}

function renderMoves() {
    const mi = state.request.moveInfo || { moves: [0,0,0,0], currentPp: [0,0,0,0], maxPp: [0,0,0,0] };
    const grid = $("moveGrid");
    grid.innerHTML = "";
    for (let i = 0; i < 4; i++) {
        const id = mi.moves[i];
        const cur = mi.currentPp[i], max = mi.maxPp[i];
        const btn = document.createElement("button");
        btn.className = "move-btn";
        btn.disabled = !id || cur === 0;
        btn.innerHTML = `<div class="move-name">Move ${id || "—"}</div>
                         <div class="move-pp">PP ${cur}/${max}</div>
                         <div class="move-pp">slot ${i} <kbd>${i+1}</kbd></div>`;
        btn.onclick = () => selectMove(i);
        grid.appendChild(btn);
    }
    updateFightSubmit();
}

function selectMove(i) {
    const mi = state.request.moveInfo;
    if (!mi.moves[i] || mi.currentPp[i] === 0) return;
    state.selectedMove = i;
    Array.from($("moveGrid").children).forEach((el, idx) => {
        el.classList.toggle("selected", idx === i);
    });
    updateFightSubmit();
}

function updateFightSubmit() {
    const ok = state.selectedMove !== null &&
        (!state.isDoubles || state.selectedTarget !== null);
    $("submitFight").disabled = !ok;
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
        const nick = (mon.nickname || "").replace(/\0.*$/, "").trim();
        const status = mon.status1 ? '<span class="badge">STS</span>' : "";
        const pct = mon.maxHp ? Math.max(0, Math.min(100, (mon.hp/mon.maxHp)*100)) : 0;
        row.innerHTML = `
            <div class="info">
                <div class="slot">slot ${i}${isCurrent ? " (active)" : ""}${fainted ? " (fainted)" : ""}</div>
                <div class="mon-species">#${mon.species} Lv${mon.level}${status}</div>
                <div class="mon-line"><span>${nick || "(no name)"}</span><span>${mon.hp}/${mon.maxHp}</span></div>
            </div>
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
        btn.innerHTML = `<span>Item #${id}</span><span class="slot">slot ${idx}</span>`;
        btn.onclick = () => submit(ACTION.ITEM, idx, 0);
        list.appendChild(btn);
    });
    if (!any) list.innerHTML = '<div class="idle-card">No trainer items available.</div>';
}

// ---- tabs + keyboard ----------------------------------------------
function switchTab(name) {
    state.activeTab = name;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".pane").forEach(p => p.classList.remove("active"));
    $("pane-" + name).classList.add("active");
}

document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));

document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t.matches('#targetPicker input[name="target"]')) {
        state.selectedTarget = t.value;
        updateFightSubmit();
    }
});

$("submitFight").addEventListener("click", () => {
    if (state.selectedMove === null) return;
    const r = state.request;
    let targetBattler = r.targetBattlerLeft;
    if (state.isDoubles && state.selectedTarget === "R") targetBattler = r.targetBattlerRight;
    submit(ACTION.FIGHT, state.selectedMove, targetBattler);
});
$("submitCancel").addEventListener("click", () => submit(ACTION.CANCEL_PARTNER, 0, 0));

document.addEventListener("keydown", (ev) => {
    if (!state.request) return;
    const k = ev.key.toLowerCase();
    if (k === "f") switchTab("fight");
    else if (k === "s") switchTab("switch");
    else if (k === "i") switchTab("item");
    else if (k === "c" && state.isDoubles) switchTab("cancel");
    else if (k === "escape") {
        state.selectedMove = null;
        state.selectedTarget = null;
        renderRequest();
    } else if (state.activeTab === "fight" && ["1","2","3","4"].includes(k)) {
        selectMove(parseInt(k, 10) - 1);
    } else if (k === "enter") {
        if (state.activeTab === "fight" && !$("submitFight").disabled) $("submitFight").click();
        else if (state.activeTab === "cancel") $("submitCancel").click();
    }
});

renderIdle();
connect();
