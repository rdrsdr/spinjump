// SpinJump UI: sends parameters/commands and shows frames and telemetry from the server.
// No physics or 3D rendering happens in the browser. Each tab has its own server-side session.
"use strict";

const FIELDS = [
  ["Tower", [
    ["tower.height_m", "Height H", "m", 5, 200, 0.5],
    ["tower.diameter_m", "Diameter D", "m", 0.5, 20, 0.1],
    ["tower.wall_friction", "Object–wall friction", "", 0, 1.5, 0.05],
  ]],
  ["Rope (wrap_tether)", [
    ["rope.length_auto", "Automatic length", "", null, null, null, "bool"],
    ["rope.length_m", "Length L", "m", 5, 400, 0.5],
    ["rope.axial_EA_N", "Axial stiffness EA", "N", 1000, 1e6, 1000],
    ["rope.axial_damping_ratio", "Damping ratio ζ", "", 0, 1, 0.01],
    ["rope.wall_friction", "Rope–wall friction", "", 0, 1.5, 0.05],
    ["rope.winding_handedness", "Helix direction", "", null, null, null, ["ccw", "cw"]],
    ["rope.winding_pitch_factor", "Pitch / diameter", "", 1, 5, 0.05],
    ["rope.linear_density_kg_m", "Linear density", "kg/m", 0, 1, 0.005],
    ["rope.wind_drag_Cd_normal", "Normal Cd", "", 0, 3, 0.05],
    ["rope.breaking_load_N", "Breaking load", "N", 1000, 100000, 500],
  ]],
  ["Object", [
    ["object.type", "Type", "", null, null, null, ["mannequin", "sandbag"]],
    ["object.mass_kg", "Mass", "kg", 5, 200, 1],
    ["object.start_clearance_m", "Initial clearance", "m", 0, 5, 0.05],
    ["object.attach_height_fraction", "Attachment (height fraction)", "", 0, 1, 0.05],
    ["object.drag_CdA_m2", "Cd·A", "m²", 0, 2, 0.05],
    ["object.geom_friction", "Object friction", "", 0, 1.5, 0.05],
  ]],
  ["Launch", [
    ["launch.mode", "Mode", "", null, null, null, ["velocity", "impulse"]],
    ["launch.speed_ms", "Speed (0–30)", "m/s", 0, 30, 0.1],
    ["launch.impulse_Ns", "Impulse J (0–2400)", "N·s", 0, 2400, 10],
    ["launch.azimuth_deg", "Azimuth (−180 to 180)", "°", -180, 180, 1],
    ["launch.elevation_deg", "Elevation", "°", -60, 60, 1],
    ["launch.duration_ms", "Duration (0 = instantaneous)", "ms", 0, 2000, 10],
  ]],
  ["Air and wind", [
    ["air.enabled", "Air drag", "", null, null, null, "bool"],
    ["wind.enabled", "Wind", "", null, null, null, "bool"],
    ["wind.preset", "Wind preset", "", null, null, null, ["", "calm", "light", "breeze", "strong"]],
    ["wind.speed_mean_ms", "Mean speed", "m/s", 0, 40, 0.5],
    ["wind.direction_deg", "Direction (blowing toward)", "°", -180, 360, 5],
    ["wind.gust_std_ms", "Gusts (std. dev.)", "m/s", 0, 10, 0.1],
    ["wind.correlation_time_s", "Gust correlation time", "s", 0.1, 60, 0.1],
    ["wind.shear_exponent", "Profile exponent", "", 0, 0.5, 0.01],
    ["wind.seed", "Seed", "", 0, 1e9, 1],
  ]],
  ["Ground and contact", [
    ["ground.preset", "Ground preset", "", null, null, null, ["", "dry_asphalt", "concrete", "grass", "wet", "ice"]],
    ["ground.friction_slide", "Sliding friction", "", 0, 1.5, 0.05],
    ["ground.friction_rolling", "Rolling resistance", "m", 0, 0.2, 0.005],
    ["contact.solref_t", "solref (time constant)", "s", 0.001, 0.1, 0.001],
  ]],
  ["Impact and run", [
    ["impact.damage_threshold_g", "Damage threshold (illustrative)", "g", 1, 200, 1],
    ["solver.max_time_s", "Maximum time", "s", 1, 300, 1],
    ["solver.stop_on_structure_hit", "Stop on tower hit", "", null, null, null, "bool"],
    ["ui.playback_factor", "Initial playback factor", "×", 0.1, 4, 0.1],
    ["ui.camera", "Initial camera", "", null, null, null, ["free", "side", "follow"]],
  ]],
];

let defaults = null;   // full configuration from the server
let current = null;    // configuration shown in the form
let ws = null;
let state = "idle";
const hist = { t: [], z: [], T: [] };

const $ = (id) => document.getElementById(id);
const get = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
function set(obj, path, v) {
  const ks = path.split("."); let o = obj;
  ks.slice(0, -1).forEach((k) => { o[k] = o[k] ?? {}; o = o[k]; });
  o[ks[ks.length - 1]] = v;
}

function buildForm(cfg) {
  const form = $("form");
  form.innerHTML = "";
  for (const [title, fields] of FIELDS) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${title}</legend>`;
    for (const [path, label, unit, min, max, step, kind] of fields) {
      const lab = document.createElement("label");
      lab.dataset.path = path;
      let input;
      if (Array.isArray(kind)) {
        input = document.createElement("select");
        kind.forEach((o) => { const op = document.createElement("option"); op.value = o; op.textContent = o || "(none)"; input.appendChild(op); });
      } else if (kind === "bool") {
        input = document.createElement("input"); input.type = "checkbox";
      } else {
        input = document.createElement("input"); input.type = "number";
        if (min !== null) input.min = min; if (max !== null) input.max = max; if (step !== null) input.step = step;
      }
      input.name = path;
      lab.innerHTML = `<span>${label}${unit ? ` <span class="unit">(${unit})</span>` : ""}</span>`;
      lab.appendChild(input);
      fs.appendChild(lab);
    }
    form.appendChild(fs);
  }
  const hint = document.createElement("p");
  hint.className = "hint"; hint.id = "launch-hint";
  form.appendChild(hint);
  fillForm(cfg);
  form.addEventListener("input", updateVisibility);
  form.addEventListener("change", updateVisibility);
}

function fillForm(cfg) {
  current = JSON.parse(JSON.stringify(cfg));
  for (const el of $("form").elements) {
    const p = el.name; if (!p) continue;
    let v;
    if (p === "rope.length_auto") v = cfg.rope.length_m === "auto";
    else if (p === "rope.length_m") v = cfg.rope.length_m === "auto" ? "" : cfg.rope.length_m;
    else if (p === "contact.solref_t") v = cfg.contact.solref[0];
    else v = get(cfg, p);
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = v ?? "";
  }
  updateVisibility();
}

function updateVisibility() {
  const f = $("form").elements;
  const mode = f["launch.mode"].value;
  f["launch.speed_ms"].closest("label").hidden = mode !== "velocity";
  f["launch.impulse_Ns"].closest("label").hidden = mode !== "impulse";
  f["rope.length_m"].disabled = f["rope.length_auto"].checked;
  const m = parseFloat(f["object.mass_kg"].value) || 0;
  let txt = "";
  if (mode === "velocity") {
    const v = parseFloat(f["launch.speed_ms"].value) || 0;
    txt = `Equivalent impulse J = m·Δv = ${(m * v).toFixed(0)} N·s.`;
  } else {
    const J = parseFloat(f["launch.impulse_Ns"].value) || 0;
    txt = `Δv = J/m = ${(m > 0 ? J / m : 0).toFixed(2)} m/s.`;
  }
  txt += " Azimuth 0° = along the free span, away from the chimney; positive = unwinding direction.";
  $("launch-hint").textContent = txt;
}

function readForm() {
  const out = {};
  const f = $("form").elements;
  for (const el of f) {
    const p = el.name; if (!p) continue;
    if (p === "rope.length_auto") continue;
    if (p === "rope.length_m") { set(out, p, f["rope.length_auto"].checked ? "auto" : parseFloat(el.value)); continue; }
    if (p === "contact.solref_t") { set(out, "contact.solref", [parseFloat(el.value), current.contact.solref[1]]); continue; }
    if (el.type === "checkbox") set(out, p, el.checked);
    else if (el.tagName === "SELECT") set(out, p, el.value === "" ? null : el.value);
    else if (el.value === "") set(out, p, null);
    else set(out, p, p === "wind.seed" ? parseInt(el.value, 10) : parseFloat(el.value));
  }
  const mode = out.launch.mode;
  if (mode === "velocity") { out.launch.impulse_Ns = null; }
  else { out.launch.speed_ms = null; }
  return out;
}

function msg(text, cls = "info") {
  const d = document.createElement("div");
  d.className = cls; d.textContent = text;
  const box = $("messages"); box.prepend(d);
  while (box.children.length > 6) box.lastChild.remove();
}

function setState(s) {
  state = s;
  $("btn-pause").disabled = s !== "running";
  $("btn-resume").disabled = s !== "paused";
  $("btn-stop").disabled = !(s === "running" || s === "paused");
}

const BADGE = { "OK": ["#0ca30c", "✓", "OK"], "ATENÇÃO": ["#fab219", "!", "WARNING"], "DANO": ["#d03b3b", "✕", "DAMAGE"] };
function badge(cls) {
  const [c, i, label] = BADGE[cls] || ["#898781", "•", cls];
  return `<span class="badge" style="border-color:${c}"><i style="background:${c}">${i}</i>${label}</span>`;
}

const TELE = [
  ["speed", "speed", "m/s", 2], ["height", "CoM height", "m", 2], ["wall_dist", "distance to wall", "m", 2],
  ["object_turns", "object turns", "", 2], ["stored_turns", "turns on helix", "", 2],
  ["wound_turns", "turns in contact", "", 2], ["wound_len", "wound rope", "m", 1],
  ["free_len", "free span", "m", 1], ["elongation", "elongation", "m", 3], ["slack", "slack", "m", 3],
  ["tension", "tension at object", "N", 0], ["tension_anchor", "tension at anchor", "N", 0],
  ["tension_max", "max tension", "N", 0], ["ground_fn", "ground normal force", "N", 0], ["tower_fn", "tower normal force", "N", 0],
];

function onTelemetry(t) {
  $("t-sim").textContent = t.t.toFixed(2);
  $("t-wall").textContent = (t.wall_s ?? 0).toFixed(2);
  $("rate").textContent = `${(t.rate ?? 0).toFixed(2)}× (requested ${t.factor.toFixed(1)}×)`;
  $("render-ms").textContent = (t.render_ms ?? 0).toFixed(0);
  $("phase").textContent = t.phase + (t.paused ? " · paused" : "");
  const dl = $("tele");
  dl.innerHTML = TELE.map(([k, lab, u, nd]) => {
    const v = t[k];
    const flag = (k === "slack" && t.slack_flag) || (k === "tension_max" && t.load_warn);
    return `<dt>${lab}${u ? ` <span class="unit">(${u})</span>` : ""}</dt><dd class="${flag ? "flag" : ""}">${v == null ? "—" : Number(v).toFixed(nd)}</dd>`;
  }).join("");
  const ev = t.events || [];
  $("events").innerHTML = ev.length ? ev.slice().reverse().map((e) =>
    `<li>${badge(e.classification)} ${e.surface === "ground" ? "ground" : "tower"} t=${Number(e.t_start).toFixed(2)} s · ${Number(e.decel_peak_g).toFixed(1)} g${e.active ? " (ongoing)" : ""}</li>`).join("")
    : `<li class="muted">none</li>`;
  hist.t.push(t.t); hist.z.push(t.height); hist.T.push(t.tension);
  if (hist.t.length > 1500) { hist.t.shift(); hist.z.shift(); hist.T.shift(); }
  spark("sp-height", hist.z, "#2a78d6"); spark("sp-tension", hist.T, "#eb6834");
  if (t.failure) msg(t.failure, "warnmsg");
}

function spark(id, ys, color) {
  const c = $(id), g = c.getContext("2d");
  const w = c.width, h = c.height;
  g.clearRect(0, 0, w, h);
  if (ys.length < 2) return;
  const mx = Math.max(...ys, 1e-9), mn = Math.min(...ys, 0);
  g.strokeStyle = color; g.lineWidth = 1.5; g.beginPath();
  ys.forEach((y, i) => {
    const X = (i / (ys.length - 1)) * (w - 2) + 1;
    const Y = h - 2 - ((y - mn) / (mx - mn || 1)) * (h - 4);
    i ? g.lineTo(X, Y) : g.moveTo(X, Y);
  });
  g.stroke();
}

function onFinished(r) {
  setState("finished");
  const o = r.outcome, sp = r.spiral, ga = r.ground_arrival, gp = r.ground_phase, ro = r.rope;
  const mx = r.impacts.max_event;
  const base = r.dir_url;
  const files = (r.artifacts || []).map((a) => `<a href="${base}${a}" target="_blank" rel="noopener">${a}</a>`).join(" · ");
  $("result").hidden = false;
  $("result").innerHTML = `<h3>Result: ${o.code}</h3><p>${o.text}</p>
    <ul>
      <li>turns before ground: <b>${sp.object_turns_before_ground ?? "—"}</b> (helix ${sp.stored_turns_initial} → ${sp.stored_turns_at_ground ?? "—"})</li>
      <li>ground arrival: <b>${ga.speed_ms ?? "—"} m/s</b></li>
      <li>slide: <b>${gp.slide_path_m ?? "—"} m</b>, swept ${gp.angle_swept_after_ground_deg ?? "—"}°</li>
      <li>max tension: <b>${ro.tension_max_N} N</b>; slack ${ro.slack_time_total_s} s</li>
      <li>largest impact: ${mx ? `${mx.decel_peak_g} g ${badge(mx.classification)}` : "none"}</li>
    </ul>
    <p><a href="${r.report_url}" target="_blank" rel="noopener"><b>Open the report</b></a></p>
    <details><summary>All files</summary><p class="files">${files}</p></details>
    <p class="hint">Reports are temporary on shared servers.</p>`;
  (r.warnings || []).forEach((w) => msg(w, "warnmsg"));
}

function showLoad(m) {
  if (m.max == null) return;
  $("server-load").textContent = `server: ${m.active}/${m.max} simulations running`;
}

function getSid() {
  try { return sessionStorage.getItem("spinjump_sid"); } catch (e) { return null; }
}
function setSid(v) {
  try { sessionStorage.setItem("spinjump_sid", v); } catch (e) { /* sem armazenamento: sessão vale só até recarregar */ }
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "blob";
  let lastUrl = null;
  ws.onopen = () => ws.send(JSON.stringify({ cmd: "hello", sid: getSid() }));
  ws.onmessage = (ev) => {
    if (typeof ev.data !== "string") {
      const url = URL.createObjectURL(ev.data);
      $("frame").src = url;
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      lastUrl = url;
      $("placeholder").hidden = true;
      return;
    }
    const m = JSON.parse(ev.data);
    if (m.type === "telemetry") {
      onTelemetry(m);
      if (m.status === "running" && state !== "paused" && state !== "running" && state !== "finished") setState("running");
    } else if (m.type === "hello") {
      setSid(m.sid);
      showLoad(m);
    } else if (m.type === "server") {
      showLoad(m);
    } else if (m.type === "started") {
      hist.t = []; hist.z = []; hist.T = [];
      $("result").hidden = true;
      setState("running");
      $("pitch-note").textContent = `(pitch magnified ×${m.helix_visual_pitch_scale}, visual only)`;
      msg(`simulation started: L = ${m.layout.rope_length_m} m (${m.layout.rope_length_source}); initial helix ${m.layout.turns0} turns`);
      (m.warnings || []).forEach((w) => msg(w, "warnmsg"));
      $("playback").value = m.factor; $("pb-out").textContent = `${Number(m.factor).toFixed(1)}×`;
      document.querySelectorAll(".cam").forEach((b) => b.classList.toggle("active", b.dataset.cam === m.camera));
    } else if (m.type === "status") {
      if (m.helix_visual_pitch_scale) $("pitch-note").textContent = `(pitch magnified ×${m.helix_visual_pitch_scale}, visual only)`;
      if (m.status === "attached") { setState(m.finished ? "finished" : (m.paused ? "paused" : "running")); msg("reconnected to your simulation"); }
      if (m.status === "paused") setState("paused");
      if (m.status === "running") setState("running");
      if (m.status === "writing" || m.status === "stopping") msg(m.message || "stopping…");
    } else if (m.type === "finished") {
      onFinished(m);
    } else if (m.type === "error") {
      msg(m.message, "err");
      if (state === "starting") setState("idle");
    }
  };
  ws.onclose = () => { msg("connection lost; reconnecting…", "warnmsg"); setTimeout(connect, 1500); };
}

const send = (o) => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));

async function init() {
  const r = await fetch("/api/defaults");
  const d = await r.json();
  defaults = d.config;
  $("safety").innerHTML = `<strong>Simulation only.</strong> ${d.safety_notice} Not instructions — do not attempt this. <a href="/">Read more</a>.`;
  if (d.server) showLoad(d.server);
  const sel = $("preset");
  d.presets.forEach((p) => { const o = document.createElement("option"); o.value = p.name; o.textContent = p.name.replace(/_/g, " "); o.title = p.description; sel.appendChild(o); });
  buildForm(defaults);
  sel.addEventListener("change", async () => {
    if (!sel.value) { fillForm(defaults); $("preset-desc").textContent = ""; return; }
    const pr = await (await fetch(`/api/preset/${sel.value}`)).json();
    if (pr.error) { msg(pr.error, "err"); return; }
    fillForm(pr.config); $("preset-desc").textContent = pr.description;
  });
  $("btn-start").onclick = () => { setState("starting"); msg("preparing your simulation and renderer…"); send({ cmd: "start", preset: $("preset").value || null, config: readForm() }); };
  $("btn-pause").onclick = () => send({ cmd: "pause" });
  $("btn-resume").onclick = () => send({ cmd: "resume" });
  $("btn-stop").onclick = () => send({ cmd: "stop" });
  $("playback").oninput = (e) => { $("pb-out").textContent = `${Number(e.target.value).toFixed(1)}×`; };
  $("playback").onchange = (e) => send({ cmd: "playback", factor: parseFloat(e.target.value) });
  document.querySelectorAll(".cam").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".cam").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); send({ cmd: "camera", mode: b.dataset.cam });
  });
  $("zoom-in").onclick = () => send({ cmd: "camera", zoom: 0.8 });
  $("zoom-out").onclick = () => send({ cmd: "camera", zoom: 1.25 });
  $("cam-up").onclick = () => send({ cmd: "camera", dz: 4 });
  $("cam-down").onclick = () => send({ cmd: "camera", dz: -4 });
  $("cam-reset").onclick = () => send({ cmd: "camera", reset: true });
  // drag = orbit (free camera); wheel = zoom — handled on the server
  const img = $("frame");
  let drag = null, acc = [0, 0], timer = null;
  img.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY]; img.setPointerCapture(e.pointerId); });
  img.addEventListener("pointermove", (e) => {
    if (!drag) return;
    acc[0] += e.clientX - drag[0]; acc[1] += e.clientY - drag[1]; drag = [e.clientX, e.clientY];
    if (!timer) timer = setTimeout(() => { send({ cmd: "camera", daz: -acc[0] * 0.3, del: -acc[1] * 0.2 }); acc = [0, 0]; timer = null; }, 60);
  });
  img.addEventListener("pointerup", () => { drag = null; });
  $("viewport").addEventListener("wheel", (e) => { e.preventDefault(); send({ cmd: "camera", zoom: e.deltaY > 0 ? 1.1 : 0.9 }); }, { passive: false });
  connect();
}
init();
