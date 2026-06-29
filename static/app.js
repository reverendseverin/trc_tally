"use strict";

const cfg = { machines: [], tallies: [], stateLabels: {}, autoCodes: [] };
const rt = { tallies: {}, machines: {} };
let es = null;

const BADGE_COLOR = {
  0: "#888", 1: "#ff5a5a", 2: "#22d36a", 3: "#ff5a5a",
  4: "#e06ae8", 5: "#22d36a", 9: "#ff5a5a", 10: "#cfcfcf",
};
const TEST_CODES = [0, 1, 2, 5, 3, 4, 9, 10];

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) { showLogin(); throw new Error("unauthorized"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function machineName(id) {
  const m = cfg.machines.find(x => x.id === id);
  return m ? m.name : "—";
}

// --------------------------------------------------------------------------- //
// auth
// --------------------------------------------------------------------------- //
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
  if (es) { es.close(); es = null; }
}
function showApp() {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pw = document.getElementById("password").value;
  const errEl = document.getElementById("login-error");
  try {
    const r = await fetch("/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    const d = await r.json();
    if (d.ok) { errEl.textContent = ""; await start(); }
    else errEl.textContent = d.error || "Incorrect password";
  } catch (_) { errEl.textContent = "Login failed"; }
});

document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/logout"); showLogin();
});

// --------------------------------------------------------------------------- //
// dashboard
// --------------------------------------------------------------------------- //
function renderDashboard() {
  const wrap = document.getElementById("dashboard");
  wrap.innerHTML = "";
  document.getElementById("dash-empty").classList.toggle("hidden", cfg.tallies.length > 0);
  for (const t of cfg.tallies) wrap.appendChild(tallyCard(t));
}

function tallyCard(t) {
  const card = el(`<div class="tcard" id="t-${t.id}">
    <div class="dev"></div>
    <span class="nm">${esc(t.name)}</span>
    <span class="sub">${esc(machineName(t.machine_id))} · in ${esc(t.input_id)}</span>
    <span class="badge"></span>
  </div>`);
  paintTally(card, t);
  return card;
}

function paintTally(card, t) {
  const code = (rt.tallies[t.id] || {}).code ?? 0;
  const label = (rt.tallies[t.id] || {}).label ?? "Off";
  card.querySelector(".dev").innerHTML = renderTallyDevice(code, t.input_id);
  const badge = card.querySelector(".badge");
  const mrt = rt.machines[t.machine_id] || {};
  const noSignal = t.machine_id && mrt.connected === false;
  const unassigned = !t.machine_id;
  card.classList.toggle("disconnected", noSignal || unassigned);
  if (noSignal) {
    badge.textContent = "No signal";
    badge.style.color = "var(--danger)";
  } else if (unassigned) {
    badge.textContent = "Unassigned";
    badge.style.color = "var(--muted)";
  } else {
    badge.textContent = label;
    badge.style.color = BADGE_COLOR[code] || "#888";
  }
}

function updateTallyCard(id) {
  const t = cfg.tallies.find(x => x.id === id);
  const card = document.getElementById("t-" + id);
  if (t && card) paintTally(card, t);
}

function updateConnForMachine(mid) {
  for (const t of cfg.tallies.filter(x => x.machine_id === mid)) updateTallyCard(t.id);
}

// --------------------------------------------------------------------------- //
// machines + assignments
// --------------------------------------------------------------------------- //
function renderMachines() {
  const grid = document.getElementById("machines");
  grid.innerHTML = "";
  for (const m of cfg.machines) grid.appendChild(machineCard(m));
  const un = document.getElementById("unassigned");
  un.innerHTML = "";
  for (const t of cfg.tallies.filter(x => !x.machine_id)) un.appendChild(tallyChip(t));
  setupDrop(un, "");
}

function machineCard(m) {
  const mode = (rt.machines[m.id] || {}).mode || "live";
  const card = el(`<div class="mcard ${mode === "manual" ? "manual" : ""}" id="m-${m.id}">
    <div class="mhead">
      <span class="conn-dot" id="mdot-${m.id}"></span>
      <span class="mname">${esc(m.name)}</span>
      <span class="spacer" style="flex:1"></span>
      <button class="btn sm ghost" data-act="edit-m">Edit</button>
      <button class="btn sm danger" data-act="del-m">Delete</button>
    </div>
    <div class="murl">${esc(m.url)} · ${esc(m.refresh_ms)}ms</div>
    <div class="mctl">
      <span class="toggle" id="mtog-${m.id}">
        <span data-mode="live">Live</span><span data-mode="manual">Manual</span>
      </span>
      <button class="btn sm" data-act="restart">Restart</button>
      <span class="murl" id="mpv-${m.id}"></span>
    </div>
    <div class="drop" id="drop-${m.id}"></div>
  </div>`);

  card.querySelector('[data-act="edit-m"]').onclick = () => editMachine(m);
  card.querySelector('[data-act="del-m"]').onclick = () => deleteMachine(m);
  card.querySelector('[data-act="restart"]').onclick = () => restartMachine(m);
  const tog = card.querySelector("#mtog-" + m.id);
  tog.querySelectorAll("span").forEach(s => {
    s.onclick = () => setMode(m.id, s.dataset.mode);
  });

  const drop = card.querySelector("#drop-" + m.id);
  for (const t of cfg.tallies.filter(x => x.machine_id === m.id)) drop.appendChild(tallyChip(t));
  setupDrop(drop, m.id);

  paintMachine(card, m.id);
  return card;
}

function paintMachine(card, mid) {
  const s = rt.machines[mid] || {};
  const mode = s.mode || "live";
  card.classList.toggle("manual", mode === "manual");
  const tog = card.querySelector("#mtog-" + mid);
  tog.querySelectorAll("span").forEach(sp =>
    sp.classList.toggle("on", sp.dataset.mode === mode));
  const dot = card.querySelector("#mdot-" + mid);
  if (dot) dot.className = "conn-dot " + (s.connected ? "ok" : "bad");
  const pv = card.querySelector("#mpv-" + mid);
  if (pv) pv.textContent = s.connected && s.active != null
    ? `PGM ${s.active}${s.preview != null ? " · PRV " + s.preview : ""}` : "";
}

function tallyChip(t) {
  const chip = el(`<div class="chip" id="chip-${t.id}" draggable="true">
    <div class="chip-head">
      <span class="grip">⠿</span>
      <span class="chip-name">${esc(t.name)}</span>
      <span class="chip-sub">in ${esc(t.input_id)} · ${t.cloud ? "cloud" : "local"}</span>
      <span class="chip-actions">
        <button class="btn sm ghost" data-act="edit-t">Edit</button>
        <button class="btn sm danger" data-act="del-t">×</button>
      </span>
    </div>
    <div class="tests"></div>
  </div>`);
  chip.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", t.id);
    e.dataTransfer.effectAllowed = "move";
  });
  chip.querySelector('[data-act="edit-t"]').onclick = () => editTally(t);
  chip.querySelector('[data-act="del-t"]').onclick = () => deleteTally(t);

  // Test buttons only for assigned tallies (their machine drives Manual mode).
  const tests = chip.querySelector(".tests");
  if (t.machine_id) {
    for (const code of TEST_CODES) {
      const b = el(`<button>${esc(cfg.stateLabels[code] || code)}</button>`);
      b.onclick = () => sendCommand(t.id, code);
      tests.appendChild(b);
    }
  } else {
    tests.remove();
  }
  return chip;
}

function setupDrop(zone, machineId) {
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", async (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    const tid = e.dataTransfer.getData("text/plain");
    if (!tid) return;
    try { await api("POST", `/api/tallies/${tid}/assign`, { machine_id: machineId || null }); }
    catch (err) { alert(err.message); }
  });
}

// --------------------------------------------------------------------------- //
// actions
// --------------------------------------------------------------------------- //
async function setMode(mid, mode) {
  try { await api("POST", `/api/machines/${mid}/mode`, { mode }); }
  catch (e) { alert(e.message); }
}
async function restartMachine(m) {
  try { await api("POST", `/api/machines/${m.id}/restart`); }
  catch (e) { alert(e.message); }
}
async function deleteMachine(m) {
  if (!confirm(`Delete machine "${m.name}"? Its tallies become unassigned.`)) return;
  await api("DELETE", `/api/machines/${m.id}`);
  await reloadConfig();
}
async function deleteTally(t) {
  if (!confirm(`Delete tally "${t.name}"?`)) return;
  await api("DELETE", `/api/tallies/${t.id}`);
  await reloadConfig();
}
async function sendCommand(tid, code) {
  try { await api("POST", `/api/tallies/${tid}/command`, { code }); }
  catch (e) { alert(e.message); }
}

// --------------------------------------------------------------------------- //
// modal forms
// --------------------------------------------------------------------------- //
function openModal(title, bodyHtml, onSave, saveLabel) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHtml;
  document.getElementById("modal").classList.remove("hidden");
  const save = document.getElementById("modal-save");
  save.textContent = saveLabel || "Save";
  save.onclick = async () => {
    save.disabled = true;
    try { if (await onSave() !== false) closeModal(); }
    finally { save.disabled = false; }
  };
}
function closeModal() { document.getElementById("modal").classList.add("hidden"); }
document.getElementById("modal-cancel").onclick = closeModal;

function val(id) { return document.getElementById(id).value.trim(); }
function checked(id) { return document.getElementById(id).checked; }

function machineForm(m) {
  return `
    <label>Name</label><input id="f-name" value="${esc(m ? m.name : "")}">
    <label>vMix API URL</label><input id="f-url" value="${esc(m ? m.url : "http://")}" placeholder="http://10.0.0.5:8088">
    <label>Refresh (ms)</label><input id="f-refresh" type="number" value="${esc(m ? m.refresh_ms : 200)}">`;
}
function addMachine() {
  openModal("Add machine", machineForm(null), async () => {
    if (!val("f-url")) { alert("URL required"); return false; }
    await api("POST", "/api/machines", { name: val("f-name") || "vMix", url: val("f-url"), refresh_ms: val("f-refresh") || 200 });
    await reloadConfig();
  });
}
function editMachine(m) {
  openModal("Edit machine", machineForm(m), async () => {
    await api("PUT", `/api/machines/${m.id}`, { name: val("f-name"), url: val("f-url"), refresh_ms: val("f-refresh") });
    await reloadConfig();
  });
}

function tallyForm(t) {
  const opts = cfg.machines.map(m =>
    `<option value="${m.id}" ${t && t.machine_id === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("");
  return `
    <label>Name</label><input id="f-name" value="${esc(t ? t.name : "")}">
    <div class="check"><input type="checkbox" id="f-cloud" ${!t || t.cloud ? "checked" : ""}><label style="margin:0">Cloud (MQTT)</label></div>
    <label>MAC address (cloud)</label><input id="f-mac" value="${esc(t ? t.mac : "")}" placeholder="AC:0B:FB:D7:EC:B0">
    <label>IP address (local)</label><input id="f-ip" value="${esc(t ? t.ip : "")}" placeholder="tally01.local">
    <label>Machine</label><select id="f-machine"><option value="">— unassigned —</option>${opts}</select>
    <label>vMix input</label>
    <select id="f-input-pick"><option value="">— pull from vMix —</option></select>
    <input id="f-input" type="number" value="${esc(t ? t.input_id : 1)}" style="margin-top:6px" title="Input number">
    <div class="muted" id="f-input-hint" style="margin-top:4px"></div>
    <div class="check"><input type="checkbox" id="f-fp" ${!t || t.fullpreview ? "checked" : ""}><label style="margin:0">Full preview (both sides green)</label></div>`;
}

function wireTallyForm() {
  const msel = document.getElementById("f-machine");
  const pick = document.getElementById("f-input-pick");
  const num = document.getElementById("f-input");
  const hint = document.getElementById("f-input-hint");
  async function load(mid) {
    pick.innerHTML = '<option value="">— pull from vMix —</option>';
    if (!mid) { hint.textContent = "Assign a machine to pull its inputs."; return; }
    hint.textContent = "Loading inputs…";
    try {
      const r = await api("GET", `/api/machines/${mid}/inputs`);
      if (!r.inputs || !r.inputs.length) {
        hint.textContent = r.error ? "Could not reach vMix." : "No inputs found.";
        return;
      }
      for (const i of r.inputs) {
        const o = document.createElement("option");
        o.value = i.number;
        o.textContent = `${i.number} — ${i.title || i.type || ""}`;
        if (String(i.number) === String(num.value)) o.selected = true;
        pick.appendChild(o);
      }
      hint.textContent = "Or type a number below.";
    } catch (_) { hint.textContent = "Could not load inputs."; }
  }
  pick.onchange = () => { if (pick.value) num.value = pick.value; };
  msel.onchange = () => load(msel.value);
  load(msel.value);
}
function tallyPayload() {
  return {
    name: val("f-name") || "Tally", cloud: checked("f-cloud"),
    mac: val("f-mac"), ip: val("f-ip"),
    machine_id: val("f-machine") || null, input_id: val("f-input") || 1,
    fullpreview: checked("f-fp"),
  };
}
function addTally() {
  openModal("Add tally", tallyForm(null), async () => {
    await api("POST", "/api/tallies", tallyPayload());
    await reloadConfig();
  });
  wireTallyForm();
}
function editTally(t) {
  openModal("Edit tally", tallyForm(t), async () => {
    await api("PUT", `/api/tallies/${t.id}`, tallyPayload());
    await reloadConfig();
  });
  wireTallyForm();
}
function provisionModal() {
  const m = cfg.mqtt || {};
  openModal("Provision tallies over USB", `
    <div style="display:flex;align-items:center;gap:8px">
      <label style="margin:0;flex:1">Serial ports</label>
      <label class="check" style="margin:0"><input type="checkbox" id="p-all"> Select all</label>
      <button class="btn sm" id="p-refresh" type="button" title="Rescan">↻ Rescan</button>
    </div>
    <div id="p-ports" style="max-height:120px;overflow:auto;border:1px solid var(--border);border-radius:8px;padding:8px;margin-top:6px">scanning…</div>
    <div class="muted" style="margin-top:4px">The same WiFi &amp; cloud settings are sent to every selected device.</div>
    <label>WiFi SSID</label><input id="p-ssid">
    <label>WiFi password</label><input id="p-pwd" type="password">
    <label>Network</label>
    <select id="p-dhcp"><option value="dhcp">DHCP (automatic)</option><option value="false">Static IP</option></select>
    <div id="p-static" class="hidden">
      <label>IP</label><input id="p-ip" placeholder="0.0.0.0">
      <label>Subnet</label><input id="p-subnet" placeholder="255.255.255.0">
      <label>Gateway</label><input id="p-gw" placeholder="0.0.0.0">
    </div>
    <label>Cloud server</label><input id="p-cs" value="${esc(m.broker_ip || "")}">
    <label>Cloud port</label><input id="p-cp" value="${esc(m.broker_port || "")}">
    <label>Mode</label>
    <select id="p-cm"><option value="1">Cloud (MQTT)</option><option value="0">Local</option></select>
    <div id="p-result" class="muted" style="margin-top:10px"></div>
    <button class="btn danger" id="p-reset" type="button" style="margin-top:8px">Erase / reset selected</button>
  `, async () => provisionRun(false), "Provision");

  const portsBox = document.getElementById("p-ports");
  const res = document.getElementById("p-result");

  function selectedPorts() {
    return [...portsBox.querySelectorAll(".p-portcb:checked")].map(c => c.value);
  }
  function settings() {
    return {
      ssid: val("p-ssid"), pwd: val("p-pwd"), dhcp: val("p-dhcp"),
      ip: val("p-ip"), subnet: val("p-subnet"), gateway: val("p-gw"),
      cloudserver: val("p-cs"), cloudport: val("p-cp"), cloudmode: val("p-cm"),
    };
  }

  // Provision (reset=false) or reset (reset=true) every selected port in turn,
  // streaming a per-port result line. Static IP is only sensible for one device,
  // so it's blocked for multi-port provisioning.
  async function provisionRun(reset) {
    const ports = selectedPorts();
    res.innerHTML = "";
    if (!ports.length) { res.textContent = "Select at least one port."; return false; }
    if (!reset) {
      if (!val("p-ssid")) { res.textContent = "WiFi SSID is required."; return false; }
      if (val("p-dhcp") === "false" && ports.length > 1) {
        res.textContent = "Static IP can only be used with a single device.";
        return false;
      }
    }
    if (reset && !confirm(`Erase stored config on ${ports.length} device(s)?`)) return;
    const cfgSettings = settings();
    for (const port of ports) {
      const line = document.createElement("div");
      line.textContent = `${port}: ${reset ? "resetting" : "sending"}…`;
      res.appendChild(line);
      try {
        const path = reset ? "/api/serial/reset" : "/api/serial/provision";
        const r = await api("POST", path, reset ? { port } : { port, ...cfgSettings });
        line.textContent = `${port}: ${r.ok ? "✓ done" : "✗ " + (r.error || "failed")}`;
        line.style.color = r.ok ? "var(--ok)" : "var(--danger)";
      } catch (e) {
        line.textContent = `${port}: ✗ ${e.message}`;
        line.style.color = "var(--danger)";
      }
    }
    return false;  // keep modal open to show results
  }

  async function loadPorts() {
    portsBox.textContent = "scanning…";
    try {
      const r = await api("GET", "/api/serial/ports");
      if (!r.ports.length) { portsBox.textContent = "No devices found."; return; }
      portsBox.innerHTML = r.ports.map(p =>
        `<label class="check" style="margin:0 0 4px"><input type="checkbox" class="p-portcb" value="${esc(p)}"> ${esc(p)}</label>`
      ).join("");
    } catch (_) { portsBox.textContent = "Error scanning ports."; }
  }

  document.getElementById("p-refresh").onclick = loadPorts;
  document.getElementById("p-all").onchange = (e) =>
    portsBox.querySelectorAll(".p-portcb").forEach(c => { c.checked = e.target.checked; });
  document.getElementById("p-dhcp").onchange = (e) =>
    document.getElementById("p-static").classList.toggle("hidden", e.target.value !== "false");
  document.getElementById("p-reset").onclick = () => provisionRun(true);
  loadPorts();
}

async function settingsModal() {
  let s = {};
  try { s = await api("GET", "/api/settings"); } catch (_) {}
  openModal("Settings", `
    <label>Web interface port</label>
    <input id="s-port" type="number" value="${esc(s.port || 8070)}">
    <div class="muted" style="margin-top:4px">Changing the port requires an app restart.</div>
    <label>Password</label>
    <input id="s-pw" type="password" placeholder="${s.has_password ? "•••••• (leave blank to keep)" : "set a password"}">
    <label>MQTT broker host / IP</label>
    <input id="s-bip" value="${esc(s.broker_ip || "")}">
    <label>MQTT broker port</label>
    <input id="s-bport" type="number" value="${esc(s.broker_port || "")}">
    <div class="muted" id="s-result" style="margin-top:8px"></div>
  `, async () => {
    try {
      const r = await api("POST", "/api/settings", {
        port: val("s-port"), password: val("s-pw"),
        broker_ip: val("s-bip"), broker_port: val("s-bport"),
      });
      await reloadConfig();
      if (r.restart_required) {
        document.getElementById("s-result").textContent =
          "Saved. Restart the app for the new web port to take effect.";
        return false;  // keep open so the restart note is visible
      }
    } catch (e) {
      document.getElementById("s-result").textContent = e.message;
      return false;
    }
  });
}

document.getElementById("add-machine").onclick = addMachine;
document.getElementById("add-tally").onclick = addTally;
document.getElementById("provision").onclick = provisionModal;
document.getElementById("settings").onclick = settingsModal;

// --------------------------------------------------------------------------- //
// data load + SSE
// --------------------------------------------------------------------------- //
async function reloadConfig() {
  const data = await api("GET", "/api/config");
  cfg.machines = data.machines;
  cfg.tallies = data.tallies;
  cfg.stateLabels = data.state_labels;
  cfg.autoCodes = data.auto_codes;
  cfg.mqtt = data.mqtt || {};
  renderDashboard();
  renderMachines();
}

async function loadState() {
  const snap = await api("GET", "/api/state");
  rt.tallies = {};
  for (const [id, v] of Object.entries(snap.tallies || {})) rt.tallies[id] = v;
  rt.machines = {};
  for (const [id, v] of Object.entries(snap.machines || {})) rt.machines[id] = v;
}

function connectSSE() {
  if (es) es.close();
  es = new EventSource("/api/events");
  es.onmessage = (ev) => {
    let e;
    try { e = JSON.parse(ev.data); } catch (_) { return; }
    if (e.type === "tally") {
      rt.tallies[e.id] = { code: e.code, label: e.label };
      updateTallyCard(e.id);
    } else if (e.type === "machine") {
      const prevMode = (rt.machines[e.id] || {}).mode;
      rt.machines[e.id] = { connected: e.connected, mode: e.mode, active: e.active, preview: e.preview };
      const card = document.getElementById("m-" + e.id);
      if (card) paintMachine(card, e.id);
      updateConnForMachine(e.id);
      setBroker(true);
    } else if (e.type === "config") {
      reloadConfig();
    }
  };
  es.onerror = () => setBroker(false);
}

function setBroker(ok) {
  const pill = document.getElementById("broker");
  pill.textContent = ok ? "live" : "reconnecting…";
  pill.className = "status-pill " + (ok ? "ok" : "bad");
}

async function start() {
  showApp();
  await reloadConfig();
  await loadState();
  renderDashboard();
  renderMachines();
  connectSSE();
  setBroker(true);
}

(async function init() {
  try {
    const s = await fetch("/api/session").then(r => r.json());
    if (s.authed) await start();
    else showLogin();
  } catch (_) { showLogin(); }
})();
