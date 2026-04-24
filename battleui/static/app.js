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
    names: { species: {}, moves: {} },
};

function loadNames() {
    fetch("/names.json")
        .then(r => r.json())
        .then(n => {
            state.names = n || { species: {}, moves: {} };
            if (state.request) renderRequest();
        })
        .catch(() => { /* non-fatal: IDs stay numeric */ });
}

function speciesName(id) {
    return (state.names.species && state.names.species[id]) || ("#" + id);
}

function spriteUrl(id) {
    const name = state.names.species && state.names.species[id];
    if (!name) return "";
    const slug = name.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!slug) return "";
    return `https://play.pokemonshowdown.com/sprites/gen3/${slug}.png`;
}

function moveName(id) {
    return (state.names.moves && state.names.moves[id]) || ("Move " + id);
}

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
function nicknameToString(n) {
    // The Lua bridge sends nickname as an array of GBA-charmap byte values.
    // We don't ship a charmap, so just render ASCII-printable bytes and
    // stop at the GBA string terminator (0xFF) or any NUL.
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

function monHTML(m) {
    if (!m || !m.maxHp) return '<div class="mon-species">—</div>';
    const pct = Math.max(0, Math.min(100, (m.hp / m.maxHp) * 100));
    const nick = nicknameToString(m.nickname);
    const status = m.status1 ? '<span class="badge">STS</span>' : "";
    const sprite = spriteUrl(m.species);
    const spriteHTML = sprite
        ? `<img class="mon-sprite" src="${sprite}" alt="" onerror="this.style.display='none'">`
        : "";
    return `
        <div class="mon-with-sprite">
            ${spriteHTML}
            <div class="mon-body">
                <div class="mon-species">${speciesName(m.species)} Lv${m.level}${status}</div>
                <div class="mon-line"><span>${nick || "(no name)"}</span><span>${m.hp}/${m.maxHp}</span></div>
                <div class="hp-bar"><div class="hp-fill ${hpClass(m.hp, m.maxHp)}" style="width:${pct}%"></div></div>
            </div>
        </div>
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

function isActionStage(mi) {
    if (!mi || !mi.moves) return true;
    return mi.moves.every(m => !m);
}

function renderMoves() {
    const mi = state.request.moveInfo || { moves: [0,0,0,0], currentPp: [0,0,0,0], maxPp: [0,0,0,0] };
    const grid = $("moveGrid");
    grid.innerHTML = "";
    const actionStage = isActionStage(mi);

    if (actionStage) {
        // The ROM is at OpponentHandleChooseAction — it only wants to know
        // FIGHT vs SWITCH vs ITEM. The real move list comes in a second
        // request a moment later. Show a big FIGHT confirmation instead.
        const hint = document.createElement("div");
        hint.className = "idle-card";
        hint.textContent = "Pick an action. Click Fight to let the opponent attack (you'll be prompted for the specific move next), or use the Switch / Item tabs.";
        grid.appendChild(hint);
        state.selectedMove = null;
    } else {
        for (let i = 0; i < 4; i++) {
            const id = mi.moves[i];
            const cur = mi.currentPp[i], max = mi.maxPp[i];
            const btn = document.createElement("button");
            btn.className = "move-btn";
            btn.disabled = !id || cur === 0;
            btn.innerHTML = `<div class="move-name">${id ? moveName(id) : "—"}</div>
                             <div class="move-pp">PP ${cur}/${max}</div>
                             <div class="move-pp">slot ${i} <kbd>${i+1}</kbd></div>`;
            btn.onclick = () => selectMove(i);
            grid.appendChild(btn);
        }
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
    const actionStage = isActionStage(state.request && state.request.moveInfo);
    if (actionStage) {
        // Fight at action-stage is a single "yes, fight" signal — no move slot
        // or target needed yet.
        $("submitFight").disabled = false;
        return;
    }
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
        const nick = nicknameToString(mon.nickname);
        const status = mon.status1 ? '<span class="badge">STS</span>' : "";
        const pct = mon.maxHp ? Math.max(0, Math.min(100, (mon.hp/mon.maxHp)*100)) : 0;
        const sprite = spriteUrl(mon.species);
        const spriteHTML = sprite
            ? `<img class="party-sprite" src="${sprite}" alt="" onerror="this.style.display='none'">`
            : "";
        row.innerHTML = `
            ${spriteHTML}
            <div class="info">
                <div class="slot">slot ${i}${isCurrent ? " (active)" : ""}${fainted ? " (fainted)" : ""}</div>
                <div class="mon-species">${speciesName(mon.species)} Lv${mon.level}${status}</div>
                <div class="mon-line"><span>${nick || "(no name)"}</span><span>${mon.hp}/${mon.maxHp}</span></div>
                <div class="hp-bar"><div class="hp-fill ${hpClass(mon.hp, mon.maxHp)}" style="width:${pct}%"></div></div>
            </div>
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
    const r = state.request;
    if (!r) return;
    if (isActionStage(r.moveInfo)) {
        // First of the two-stage flow: the ROM just wants FIGHT vs SWITCH/ITEM.
        submit(ACTION.FIGHT, 0, 0);
        return;
    }
    if (state.selectedMove === null) return;
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
loadNames();
connect();
