// pokeemeraldplus randomizer - frontend
// Plain ES2020, no framework. Single file orchestrates:
//   - router (left-nav)
//   - state (config mirror of BuildConfigModel)
//   - bindings (DOM <-> state, debounced preview refresh)
//   - build runner (SSE log streaming)
//   - evolution graph render
//   - presets (localStorage)

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------- Default state (shape mirrors BuildConfigModel) ----------
const defaultConfig = () => ({
    seed: "",
    randomize_wild: false,
    randomize_starters: false,
    randomize_trainers: false,
    random_mode: "global",
    level_scale: {
        wild_percent: 0,
        trainer_percent: 0,
        wild_fixed_level: null,
        trainer_fixed_level: null,
        starter_level: 5,
    },
    randomize_level_up_moves: false,
    randomize_egg_moves: false,
    randomize_tm_moves: false,
    randomize_tutor_moves: false,
    randomize_tmhm_compat: false,
    randomize_tutor_compat: false,
    moves_prefer_same_type: false,
    moves_good_damaging_percent: 0,
    moves_block_broken: false,
    guaranteed_starting_moves: 0,
    evo_mode: "vanilla",
    evo_constraints: {
        max_indegree: null,
        max_cycle_length: null,
        min_cycle_length: null,
        min_cycles: null,
        max_avg_indegree: null,
        max_tree_depth: null,
    },
    fast_evolution_anim: false,
    prevent_evolution_cancel: false,
    nuzlocke_delete_fainted: false,
    force_doubles: false,
    steal_trainer_team: false,
    no_exp: false,
    negative_exp: false,
    no_pokeballs: false,
    money_for_moves: false,
    start_with_super_rare_candy: false,
    walk_through_walls: false,
    webui_opponent: false,
    opponent_stat_stage_mod: 0,
    player_stat_stage_mod: 0,
    gym_leader_first_roster: 0,
    walk_fast: false,
    instant_text: false,
    fast_battle_anims: false,
    skip_battle_transition: false,
    skip_intro_cutscene: false,
    fast_intro: false,
    skip_fade_anims: false,
    fast_stat_anims: false,
    manual_battle_text: false,
    wait_time_divisor_pow: 0,
});

const state = {
    config: defaultConfig(),
    buildOpts: { run_randomize: true, run_make: true, jobs: null },
    currentRun: null,
};

// ---------- Path helpers (dotted paths like "level_scale.wild_percent") ----------
function getPath(obj, path) {
    return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}
function setPath(obj, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    const parent = keys.reduce((o, k) => (o[k] = o[k] ?? {}, o[k]), obj);
    parent[last] = value;
}

// ---------- Router ----------
const navItems = $$(".nav-item");
const panels = $$(".panel");
const titleEl = $("#section-title");
function showSection(name) {
    navItems.forEach(b => b.classList.toggle("active", b.dataset.section === name));
    panels.forEach(p => p.classList.toggle("hidden", p.dataset.section !== name));
    const active = navItems.find(b => b.dataset.section === name);
    if (active) titleEl.textContent = active.textContent.trim();
    try { history.replaceState(null, "", "#" + name); } catch (_) {}
}
navItems.forEach(b => b.addEventListener("click", () => showSection(b.dataset.section)));
showSection(((location.hash || "#randomizer").slice(1)) || "randomizer");

// ---------- Health ----------
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
    } catch {
        healthPill.classList.add("err");
        healthText.textContent = "offline";
    }
})();

// ---------- Log drawer ----------
const drawer = $("#log-drawer");
const logBody = $("#log-body");
const logStatusEl = $("#log-status");
const logLed = $("#log-led");

$("#log-toggle").addEventListener("click", () => drawer.classList.toggle("collapsed"));
$("#log-close").addEventListener("click", () => drawer.classList.add("collapsed"));
$("#log-clear").addEventListener("click", () => { logBody.innerHTML = ""; });
$("#log-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(logBody.innerText); } catch {}
});

const ANSI_RE = /\x1b\[([0-9;]*)m/g;
function ansiToHtml(raw) {
    let html = "", last = 0, fg = null, bold = false, spanOpen = false;
    const open = () => {
        const cls = [];
        if (fg !== null) cls.push("ansi-" + fg);
        if (bold) cls.push("ansi-bold");
        return cls.length ? `<span class="${cls.join(" ")}">` : "";
    };
    const close = () => (fg !== null || bold) ? "</span>" : "";
    const flushOpen = () => {
        if (spanOpen) { html += close(); spanOpen = false; }
        const o = open(); if (o) { html += o; spanOpen = true; }
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
    div.innerHTML = ansiToHtml(String(text));
    logBody.appendChild(div);
    while (logBody.childElementCount > LINE_CAP) logBody.removeChild(logBody.firstChild);
    const atBottom = logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight < 40;
    if (atBottom) logBody.scrollTop = logBody.scrollHeight;
}
const log = {
    line: appendLine,
    info:    (t) => appendLine(t, "info"),
    success: (t) => appendLine(t, "success"),
    warn:    (t) => appendLine(t, "warn"),
    error:   (t) => appendLine(t, "error"),
    clear:   () => { logBody.innerHTML = ""; },
};
function setLogStatus(state, label) {
    logLed.classList.remove("running", "ok", "err");
    if (state) logLed.classList.add(state);
    logStatusEl.textContent = label;
}

// ---------- API wrappers ----------
const api = {
    async preview(body) {
        const r = await fetch("/api/preview", { method: "POST",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    async build(body) {
        const r = await fetch("/api/build", { method: "POST",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    async stop(runId) { await fetch(`/api/runs/${runId}/stop`, { method: "POST" }); },
    async renderGraph() {
        const r = await fetch("/api/evolution-graph", { method: "POST" });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    stream(runId, { onLine, onStep, onDone, onError }) {
        const es = new EventSource(`/api/runs/${runId}/events`);
        es.addEventListener("line", (e) => onLine && onLine(JSON.parse(e.data)));
        es.addEventListener("step", (e) => onStep && onStep(JSON.parse(e.data)));
        es.addEventListener("step_done", (e) => onStep && onStep({ ...JSON.parse(e.data), done: true }));
        es.addEventListener("error", (e) => {
            if (e && e.data) { try { onError && onError(JSON.parse(e.data)); } catch {} }
        });
        es.addEventListener("done", (e) => { onDone && onDone(JSON.parse(e.data)); es.close(); });
        return es;
    },
};

// ---------- Bindings ----------
function parseMaybeNumber(input) {
    const v = input.value.trim();
    if (v === "") return null;
    const n = (input.step && input.step !== "1") ? parseFloat(v) : parseInt(v, 10);
    return isNaN(n) ? null : n;
}

// Checkboxes & number/range inputs with data-bind="path"
function wireBindings() {
    $$("[data-bind]").forEach((el) => {
        const path = el.dataset.bind;
        const current = getPath(state.config, path);

        if (el.type === "checkbox") {
            el.checked = !!current;
            el.addEventListener("change", () => {
                setPath(state.config, path, el.checked);
                onConfigChanged();
            });
        } else if (el.type === "range" || el.type === "number") {
            if (current !== null && current !== undefined) el.value = String(current);
            el.addEventListener("input", () => {
                const isNumberField = el.type === "number"
                    && (el.placeholder === "—" || el.placeholder === "auto");
                // Optional fields (placeholder "—") store null when empty.
                let val;
                if (el.placeholder === "—") {
                    val = parseMaybeNumber(el);
                } else if (el.type === "range") {
                    val = parseInt(el.value, 10);
                } else {
                    val = parseMaybeNumber(el) ?? 0;
                }
                setPath(state.config, path, val);
                // Sync twin inputs (range + number mirror).
                $$(`[data-bind="${path}"]`).forEach((sibling) => {
                    if (sibling !== el) sibling.value = el.value;
                });
                onConfigChanged();
            });
        } else if (el.type === "text") {
            el.value = current ?? "";
            el.addEventListener("input", () => {
                setPath(state.config, path, el.value.trim());
                onConfigChanged();
            });
        }
    });

    $$("[data-bind-radio]").forEach((el) => {
        const path = el.dataset.bindRadio;
        const current = getPath(state.config, path);
        if (el.value === current) el.checked = true;
        el.addEventListener("change", () => {
            if (el.checked) {
                setPath(state.config, path, el.value);
                onConfigChanged();
            }
        });
    });
}

// ---------- Debounced preview refresh ----------
let previewTimer = null;
const previewPane = $("#preview-pane");

function debouncedPreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 120);
}

async function refreshPreview() {
    try {
        const body = {
            config: state.config,
            run_randomize: state.buildOpts.run_randomize,
            run_make: state.buildOpts.run_make,
            jobs: state.buildOpts.jobs,
        };
        const resp = await api.preview(body);
        if (!resp.steps.length) {
            previewPane.textContent = "# Nothing will run.";
            return;
        }
        previewPane.textContent = resp.steps.map((s) => {
            const argv = s.argv.map(quoteIfNeeded).join(" ");
            return `# ${s.label}\n${argv}`;
        }).join("\n\n");
    } catch (e) {
        previewPane.textContent = "# Error: " + e.message;
    }
}
function quoteIfNeeded(a) {
    return /[\s"'$`\\]/.test(a) ? `'${a.replace(/'/g, "'\\''")}'` : a;
}

function onConfigChanged() {
    updateEvoConstraintsEnabled();
    updateWaitDivisorLabel();
    updateStatMirror();
    updateLevelLink();
    debouncedPreview();
}

// ---------- Cross-field UI sync ----------
function updateEvoConstraintsEnabled() {
    const enabled = state.config.evo_mode === "hardcoded";
    const group = $("#evo-constraints-group");
    if (!group) return;
    group.style.opacity = enabled ? "1" : "0.45";
    $$("#evo-constraints-group input").forEach((i) => { i.disabled = !enabled; });
}

function updateWaitDivisorLabel() {
    const p = state.config.wait_time_divisor_pow | 0;
    const lbl = $("#wait-divisor-label");
    if (lbl) lbl.textContent = `${1 << p}× base (${p === 0 ? "slowest" : "faster"})`;
}

let mirroringStats = false;
function updateStatMirror() {
    const cb = $("#stat-mirror");
    if (!cb || !cb.checked || mirroringStats) return;
    mirroringStats = true;
    state.config.player_stat_stage_mod = -state.config.opponent_stat_stage_mod;
    $$('[data-bind="player_stat_stage_mod"]').forEach((e) => {
        e.value = String(state.config.player_stat_stage_mod);
    });
    mirroringStats = false;
}

let linkingLevels = false;
function updateLevelLink() {
    const cb = $("#level-link");
    if (!cb || !cb.checked || linkingLevels) return;
}

// Direct listeners for cross-field helpers (not data-bound).
function wireCrossField() {
    const wildInputs = $$('[data-bind="level_scale.wild_percent"]');
    const trnInputs  = $$('[data-bind="level_scale.trainer_percent"]');
    const link = $("#level-link");
    function sync(src, dst) {
        if (!link.checked) return;
        state.config.level_scale[dst] = state.config.level_scale[src];
        const path = `level_scale.${dst}`;
        $$(`[data-bind="${path}"]`).forEach((i) => {
            i.value = String(state.config.level_scale[dst]);
        });
    }
    wildInputs.forEach((i) => i.addEventListener("input", () => sync("wild_percent", "trainer_percent")));
    trnInputs.forEach((i) => i.addEventListener("input", () => sync("trainer_percent", "wild_percent")));

    const mirror = $("#stat-mirror");
    const opp = $$('[data-bind="opponent_stat_stage_mod"]');
    const plr = $$('[data-bind="player_stat_stage_mod"]');
    function statSync() {
        if (!mirror.checked) return;
        const v = -state.config.opponent_stat_stage_mod;
        state.config.player_stat_stage_mod = v;
        plr.forEach((i) => { i.value = String(v); });
        debouncedPreview();
    }
    opp.forEach((i) => i.addEventListener("input", statSync));

    $("#qol-enable-all").addEventListener("click", () => {
        ["walk_fast","instant_text","fast_battle_anims","skip_battle_transition","skip_intro_cutscene","fast_intro",
         "skip_fade_anims","fast_stat_anims"].forEach((k) => { state.config[k] = true; });
        wireBindings(); // re-sync checkboxes
        $$("[data-bind]").forEach((el) => {
            if (el.type === "checkbox") el.checked = !!getPath(state.config, el.dataset.bind);
        });
        debouncedPreview();
    });
    $("#qol-clear-all").addEventListener("click", () => {
        ["walk_fast","instant_text","fast_battle_anims","skip_battle_transition","skip_intro_cutscene","fast_intro",
         "skip_fade_anims","fast_stat_anims","manual_battle_text"].forEach((k) => {
            state.config[k] = false;
        });
        state.config.wait_time_divisor_pow = 0;
        $$("[data-bind]").forEach((el) => {
            if (el.type === "checkbox") el.checked = !!getPath(state.config, el.dataset.bind);
            else if (el.type === "range" || el.type === "number") {
                const v = getPath(state.config, el.dataset.bind);
                if (v !== null && v !== undefined) el.value = String(v);
            }
        });
        debouncedPreview();
    });
}

// ---------- Build opts bindings ----------
function wireBuildOpts() {
    const runR = $("#opt-run-randomize"), runM = $("#opt-run-make");
    const jobs = $("#opt-jobs");
    runR.checked = state.buildOpts.run_randomize;
    runM.checked = state.buildOpts.run_make;
    runR.addEventListener("change", () => { state.buildOpts.run_randomize = runR.checked; debouncedPreview(); });
    runM.addEventListener("change", () => { state.buildOpts.run_make = runM.checked; debouncedPreview(); });
    jobs.addEventListener("input", () => {
        const v = parseInt(jobs.value, 10);
        state.buildOpts.jobs = isNaN(v) ? null : v;
        debouncedPreview();
    });
}

// ---------- Build/Stop ----------
function wireBuild() {
    const buildBtn = $("#build-btn"), stopBtn = $("#stop-btn");
    const statusEl = $("#build-status");

    buildBtn.addEventListener("click", async () => {
        drawer.classList.remove("collapsed");
        log.clear();
        log.info(`[${new Date().toLocaleTimeString()}] starting build…`);
        setLogStatus("running", "running");
        statusEl.textContent = "building…";
        buildBtn.disabled = true;
        stopBtn.disabled = false;

        try {
            const body = {
                config: state.config,
                run_randomize: state.buildOpts.run_randomize,
                run_make: state.buildOpts.run_make,
                jobs: state.buildOpts.jobs,
            };
            const { run_id } = await api.build(body);
            state.currentRun = run_id;

            api.stream(run_id, {
                onStep: (ev) => {
                    if (ev.done) log.info(`[step ${ev.index + 1} exited ${ev.exit_code}]`);
                    else log.info(`\u25B6 step ${ev.index + 1}/${ev.total}: ${ev.label}`);
                },
                onLine: (ev) => log.line(ev.text),
                onError: (ev) => log.error(ev.message || String(ev)),
                onDone: (ev) => {
                    state.currentRun = null;
                    buildBtn.disabled = false;
                    stopBtn.disabled = true;
                    if (ev.cancelled) {
                        log.warn("cancelled.");
                        setLogStatus("err", "cancelled");
                        statusEl.textContent = "cancelled";
                    } else if (ev.exit_code === 0) {
                        log.success("build complete ✓");
                        setLogStatus("ok", "done");
                        statusEl.textContent = "done ✓";
                    } else {
                        log.error(`failed (exit ${ev.exit_code})`);
                        setLogStatus("err", `failed (${ev.exit_code})`);
                        statusEl.textContent = `failed (${ev.exit_code})`;
                    }
                },
            });
        } catch (e) {
            log.error(e.message);
            buildBtn.disabled = false;
            stopBtn.disabled = true;
            setLogStatus("err", "error");
            statusEl.textContent = "error";
        }
    });

    stopBtn.addEventListener("click", async () => {
        if (!state.currentRun) return;
        await api.stop(state.currentRun);
        log.warn("stop requested…");
    });

    $("#build-clear-btn").addEventListener("click", () => log.clear());
}

// ---------- Evolution graph render ----------
function wireGraphRender() {
    const btn = $("#render-graph-btn");
    const status = $("#render-graph-status");
    const container = $("#render-graph-container");
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        status.textContent = "rendering…";
        container.innerHTML = "";
        try {
            const r = await api.renderGraph();
            const img = new Image();
            img.src = r.image_url + "?t=" + Date.now();
            img.style.maxWidth = "100%";
            img.style.border = "1px solid var(--border)";
            img.style.borderRadius = "var(--radius)";
            container.appendChild(img);
            status.textContent = "✓ rendered";
        } catch (e) {
            status.textContent = "✗ " + (e.message.length > 100 ? e.message.slice(0, 100) + "…" : e.message);
            log.error("evolution-graph: " + e.message);
            drawer.classList.remove("collapsed");
        } finally {
            btn.disabled = false;
        }
    });
}

// ---------- Presets (localStorage) ----------
const PRESETS_KEY = "pokeemeraldplus.presets.v1";
function loadPresets() {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY)) || {}; } catch { return {}; }
}
function savePresets(map) { localStorage.setItem(PRESETS_KEY, JSON.stringify(map)); }

function wirePresets() {
    const modal = $("#preset-modal");
    const list = $("#preset-list");
    const nameInput = $("#preset-name");

    $("#preset-menu-btn").addEventListener("click", () => { renderPresetList(); modal.classList.remove("hidden"); });
    $("#preset-close").addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.add("hidden"); });

    $("#preset-save").addEventListener("click", () => {
        const name = nameInput.value.trim();
        if (!name) return;
        const presets = loadPresets();
        presets[name] = { config: state.config, buildOpts: state.buildOpts };
        savePresets(presets);
        nameInput.value = "";
        renderPresetList();
    });

    function renderPresetList() {
        const presets = loadPresets();
        const names = Object.keys(presets).sort();
        list.innerHTML = "";
        if (names.length === 0) {
            list.innerHTML = `<li class="empty" style="padding:20px;">No presets yet. Save the current settings above.</li>`;
            return;
        }
        for (const name of names) {
            const li = document.createElement("li");
            li.className = "preset-item";
            li.innerHTML = `
                <span class="preset-name"></span>
                <span class="preset-actions">
                    <button class="btn btn-ghost preset-load">Load</button>
                    <button class="btn btn-ghost preset-delete">Delete</button>
                </span>`;
            li.querySelector(".preset-name").textContent = name;
            li.querySelector(".preset-load").addEventListener("click", () => {
                const p = presets[name];
                state.config = Object.assign(defaultConfig(), p.config);
                state.config.level_scale = Object.assign(defaultConfig().level_scale, p.config.level_scale);
                state.buildOpts = Object.assign({ run_randomize: true, run_make: true, jobs: null }, p.buildOpts);
                applyStateToDom();
                debouncedPreview();
                modal.classList.add("hidden");
            });
            li.querySelector(".preset-delete").addEventListener("click", () => {
                if (!confirm(`Delete preset "${name}"?`)) return;
                const p = loadPresets(); delete p[name]; savePresets(p);
                renderPresetList();
            });
            list.appendChild(li);
        }
    }
}

function applyStateToDom() {
    $$("[data-bind]").forEach((el) => {
        const v = getPath(state.config, el.dataset.bind);
        if (el.type === "checkbox") el.checked = !!v;
        else if (el.type === "range" || el.type === "number") {
            el.value = (v === null || v === undefined) ? "" : String(v);
        } else if (el.type === "text") {
            el.value = v ?? "";
        }
    });
    $$("[data-bind-radio]").forEach((el) => {
        el.checked = el.value === getPath(state.config, el.dataset.bindRadio);
    });
    $("#opt-run-randomize").checked = state.buildOpts.run_randomize;
    $("#opt-run-make").checked      = state.buildOpts.run_make;
    $("#opt-jobs").value = state.buildOpts.jobs == null ? "" : String(state.buildOpts.jobs);
    updateEvoConstraintsEnabled();
    updateWaitDivisorLabel();
}

// ---------- Bootstrap ----------
wireBindings();
wireCrossField();
wireBuildOpts();
wireBuild();
wireGraphRender();
wirePresets();
updateEvoConstraintsEnabled();
updateWaitDivisorLabel();
refreshPreview();
