/* CSAT web UI: renders the session, all scoring comes from the Python core. */
"use strict";

const S = { session: null, analysis: null, K: null, path: null, step: "case", syncing: 0 };

const STEPS = [
  { id: "case", n: "0", t: "Case",                s: "IOC, context, TLP" },
  { id: "ach",  n: "1", t: "ACH",                 s: "Competing hypotheses" },
  { id: "kac",  n: "2", t: "Key Assumptions",     s: "What must be true?" },
  { id: "iw",   n: "3", t: "Indicators & Warnings", s: "What would we see?" },
  { id: "da",   n: "4", t: "Devil's Advocacy",    s: "Attack the conclusion" },
  { id: "report", n: "★", t: "Report",            s: "Dashboard & export" },
];

/* ── helpers ─────────────────────────────────────────────────────────── */

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function getPath(path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), S.session);
}
function setPath(path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  const obj = keys.reduce((o, k) => o[k], S.session);
  obj[last] = value;
}

async function api(url, body) {
  const res = await fetch(url, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), err ? 5000 : 2200);
}

function confColor(label) {
  return { HIGH: "var(--green)", MEDIUM: "var(--gold)", LOW: "var(--orange)", MINIMAL: "var(--red)" }[label] || "var(--dim)";
}
function confLabel(pct) {
  if (pct == null) return ["", ""];
  for (const [lo, hi, label, desc] of S.K.confidence) if (pct >= lo && pct <= hi) return [label, desc];
  return ["", ""];
}
function hName(i) {
  const h = S.session.ach.hypotheses[i];
  return h ? `H${i + 1}${h.label ? " · " + h.label : ""}` : "";
}

/* ── state sync ──────────────────────────────────────────────────────── */

let syncTimer = null;
function scheduleSync() {
  clearTimeout(syncTimer);
  setSaveState("pending");
  syncTimer = setTimeout(syncNow, 350);
}
async function syncNow() {
  clearTimeout(syncTimer);
  const ticket = ++S.syncing;
  try {
    const r = await api("/api/update", { session: S.session });
    if (ticket !== S.syncing) return; // a newer edit is in flight
    S.analysis = r.analysis;
    S.path = r.path;
    refreshLive();
    setSaveState(r.saved ? "saved" : "unsaved");
  } catch (e) {
    setSaveState("error");
    toast("Sync failed: " + e.message, true);
  }
}
function load(payload) {
  S.session = payload.session;
  S.analysis = payload.analysis;
  S.path = payload.path;
  if (payload.constants) S.K = payload.constants;
  render();
  setSaveState(S.path ? "saved" : "unsaved");
}
function setSaveState(st) {
  const el = $("#saveState");
  const txt = {
    pending: ["Saving…", ""],
    saved: [`✓ Autosaved · ${S.path}`, "ok"],
    unsaved: ["● Not saved yet", "warn"],
    error: ["⚠ Save error", "warn"],
  }[st];
  if (st === "pending" && !S.path) return setSaveState("unsaved");
  el.textContent = txt[0];
  el.className = "savestate " + txt[1];
}

/* ── live regions (re-rendered after each analysis) ──────────────────── */

const LIVE = {};
function live(name, fn) {
  LIVE[name] = fn;
  return `<div data-live="${name}">${fn()}</div>`;
}
function refreshLive() {
  document.querySelectorAll("[data-live]").forEach((el) => {
    const fn = LIVE[el.dataset.live];
    if (fn) el.innerHTML = fn();
  });
  renderChrome();
}

/* ── chrome: top bar + step nav ──────────────────────────────────────── */

function renderChrome() {
  const m = S.session.meta;
  $("#caseInfo").innerHTML = `
    <span class="badge tlp-${esc(m.tlp)}" style="${tlpStyle(m.tlp)}">TLP:${esc(m.tlp)}</span>
    <b>${esc(m.case_id || "Untitled case")}</b>
    ${m.ioc ? `<span class="ioc">${esc(m.ioc)}</span>` : ""}`;
  const done = S.analysis.completion;
  const map = { case: done.meta, ach: done.ach, kac: done.kac, iw: done.iw, da: done.da };
  $("#steps").innerHTML = STEPS.map((st, i) => `
    ${i === STEPS.length - 1 ? '<div class="sep"></div>' : ""}
    <button class="step ${S.step === st.id ? "active" : ""} ${map[st.id] ? "done" : ""}" data-action="goto" data-step="${st.id}">
      <span class="num">${map[st.id] ? "✓" : st.n}</span>
      <span><div class="t">${st.t}</div><div class="s">${st.s}</div></span>
    </button>`).join("");
}
function tlpStyle(t) {
  return {
    RED: "background:#ff2b2b;color:#fff", "AMBER+STRICT": "background:#ffc000;color:#000",
    AMBER: "background:#ffc000;color:#000", GREEN: "background:#33ff00;color:#000",
    CLEAR: "background:#fff;color:#000",
  }[t] || "";
}

function render() {
  renderChrome();
  const p = PANELS[S.step]();
  $("#panel").innerHTML = p;
  window.scrollTo({ top: 0 });
}

/* ── generic form controls ───────────────────────────────────────────── */

function field(label, path, opts = {}) {
  const v = getPath(path) ?? "";
  const ph = opts.ph ? ` placeholder="${esc(opts.ph)}"` : "";
  const ctl = opts.area
    ? `<textarea data-path="${path}"${ph} rows="${opts.rows || 3}">${esc(v)}</textarea>`
    : `<input data-path="${path}" value="${esc(v)}"${ph} class="${opts.mono ? "mono" : ""}">`;
  return label ? `<label class="f"><span>${label}</span>${ctl}</label>` : ctl;
}
function seg(path, values, cls = "", labels = null) {
  const cur = getPath(path);
  return `<div class="seg ${cls}">${values.map((v, i) =>
    `<button data-action="set" data-path="${path}" data-v="${esc(v)}" class="${cur === v ? "on" : ""}">${esc(labels ? labels[i] : v)}</button>`
  ).join("")}</div>`;
}
function rangeRow(label, path, min, max) {
  const v = getPath(path);
  return `<div class="range-row"><span>${label}</span>
    <input type="range" min="${min}" max="${max}" value="${v}" data-path="${path}" data-type="int" data-echo>
    <b>${v}</b></div>`;
}
function helpBox(title, items) {
  return `<details class="help"><summary>${title}</summary><ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul></details>`;
}
function head(kicker, title, desc, right = "") {
  return `<div class="panel-head"><div><div class="kicker">${kicker}</div><h2>${title}</h2>${desc ? `<p>${desc}</p>` : ""}</div>${right}</div>`;
}
function nextBtn(step, label) {
  return `<div class="next"><button class="btn primary" data-action="goto" data-step="${step}">${label} →</button></div>`;
}
function strList(path, ph) {
  const arr = getPath(path) || [];
  return arr.map((_, i) => `<div class="row list-row">${field("", `${path}.${i}`, { ph })}
      <button class="icon" data-action="del-item" data-path="${path}" data-i="${i}" title="Remove">✕</button></div>`).join("")
    + `<button class="btn add small" data-action="add-item" data-path="${path}">+ Add</button>`;
}

/* ── charts (SVG) ────────────────────────────────────────────────────── */

function achChart() {
  const a = S.analysis.ach;
  if (!a.ready) return "";
  const rows = [...a.hypotheses].sort((x, y) => x.rank - y.rank);
  const max = Math.max(1, ...rows.map((r) => r.inconsistency));
  const W = 520, rowH = 34, left = 150, barW = W - left - 70;
  const svg = rows.map((r, i) => {
    const y = 26 + i * rowH;
    const w = Math.max(3, (r.inconsistency / max) * barW);
    const lead = r.index === a.leader;
    const fill = r.unscored ? "none" : lead ? "var(--gold)" : "var(--dim)";
    const stroke = r.unscored ? `stroke="var(--dim)" stroke-dasharray="4 3"` : "";
    const name = (S.session.ach.hypotheses[r.index].label || "").slice(0, 16);
    return `
      <text x="0" y="${y + 15}" class="${lead ? "strong" : ""}">#${r.rank}  H${r.index + 1} ${esc(name)}</text>
      <rect x="${left}" y="${y + 3}" width="${r.unscored ? barW : w}" height="18" rx="4" fill="${fill}" ${stroke} opacity="${lead ? 1 : .7}"/>
      <text x="${left + (r.unscored ? barW : w) + 8}" y="${y + 16}" class="${lead ? "strong" : ""}">${r.unscored ? "untested" : r.inconsistency}</text>`;
  }).join("");
  return `<div class="chart"><svg viewBox="0 0 ${W} ${30 + rows.length * rowH}">
    <text x="${left}" y="12">Weighted inconsistency (shorter is stronger)</text>${svg}</svg></div>`;
}

function kacChart() {
  const A = S.session.kac.assumptions;
  const cell = 64, pad = 44, W = pad + cell * 5 + 10, H = cell * 5 + 40;
  let g = "";
  for (let imp = 1; imp <= 5; imp++) {
    for (let cert = 1; cert <= 5; cert++) {
      const risk = (6 - cert) * imp;
      const col = risk >= 16 ? "rgba(248,81,73,.42)" : risk >= 10 ? "rgba(227,134,59,.3)" : risk >= 5 ? "rgba(201,162,39,.14)" : "rgba(63,185,80,.1)";
      g += `<rect x="${pad + (cert - 1) * cell}" y="${(5 - imp) * cell}" width="${cell - 3}" height="${cell - 3}" rx="6" fill="${col}"/>`;
    }
  }
  const groups = {};
  A.forEach((a, i) => (groups[`${a.certainty}_${a.impact}`] ||= []).push(i));
  let dots = "";
  Object.values(groups).forEach((idxs) => idxs.forEach((i, k) => {
    const a = A[i];
    const n = idxs.length, cols = Math.ceil(Math.sqrt(n));
    const dx = (k % cols - (cols - 1) / 2) * 22, dy = (Math.floor(k / cols) - (Math.ceil(n / cols) - 1) / 2) * 22;
    const cx = pad + (a.certainty - 1) * cell + cell / 2 - 1.5 + dx, cy = (5 - a.impact) * cell + cell / 2 - 1.5 + dy;
    const crit = a.certainty <= 2 && a.impact >= 4;
    dots += `<circle cx="${cx}" cy="${cy}" r="10" fill="${crit ? "var(--red)" : "var(--card2)"}" stroke="${crit ? "#fff" : "var(--gold)"}" stroke-width="1.2"/>
      <text x="${cx}" y="${cy + 3.5}" text-anchor="middle" style="fill:${crit ? "#fff" : "var(--gold)"};font-size:9.5px;font-weight:700">A${i + 1}</text>`;
  }));
  const ax = [1, 2, 3, 4, 5].map((v) =>
    `<text x="${pad + (v - 1) * cell + cell / 2}" y="${cell * 5 + 14}" text-anchor="middle">${v}</text>
     <text x="${pad - 12}" y="${(5 - v) * cell + cell / 2 + 3}" text-anchor="middle">${v}</text>`).join("");
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}">${g}${dots}${ax}
    <text x="${pad + cell * 2.5}" y="${cell * 5 + 32}" text-anchor="middle" class="strong">Certainty →</text>
    <text transform="translate(12 ${cell * 2.5}) rotate(-90)" text-anchor="middle" class="strong">Impact if wrong →</text></svg></div>`;
}

function gauge(pct, label, status, size = 120) {
  const r = 46, c = Math.PI * r, off = c * (1 - pct / 100);
  const col = status === "REFUTED" ? "var(--red)" : confColor(label);
  return `<svg viewBox="0 0 120 72" width="${size}"><path d="M14 64 A46 46 0 0 1 106 64" fill="none" stroke="var(--line)" stroke-width="10" stroke-linecap="round"/>
    <path d="M14 64 A46 46 0 0 1 106 64" fill="none" stroke="${col}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"/>
    <text x="60" y="58" text-anchor="middle" style="fill:var(--text);font-size:19px;font-weight:700">${pct}%</text></svg>`;
}

function radar() {
  const ch = S.session.da.challenges;
  const n = ch.length, cx = 160, cy = 150, R = 105;
  const pt = (i, v) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [cx + Math.cos(ang) * R * v, cy + Math.sin(ang) * R * v];
  };
  let grid = "";
  for (let l = 1; l <= 5; l++) grid += `<polygon points="${ch.map((_, i) => pt(i, l / 5).join(",")).join(" ")}" fill="none" stroke="var(--line)"/>`;
  const axes = ch.map((c, i) => {
    const [x, y] = pt(i, 1), [lx, ly] = pt(i, 1.2);
    const anchor = Math.abs(lx - cx) < 10 ? "middle" : lx > cx ? "start" : "end";
    return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--line)"/>
      <text x="${lx}" y="${ly + 4}" text-anchor="${anchor}" class="${c.argument && c.strength >= 4 ? "strong" : ""}">${esc(c.area)}</text>`;
  }).join("");
  const vals = ch.map((c, i) => pt(i, (c.argument ? c.strength : 0) / 5).join(",")).join(" ");
  const dots = ch.map((c, i) => {
    const [x, y] = pt(i, (c.argument ? c.strength : 0) / 5);
    return c.argument ? `<circle cx="${x}" cy="${y}" r="4" fill="${c.strength >= 4 ? "var(--red)" : "var(--gold)"}"/>` : "";
  }).join("");
  return `<div class="chart"><svg viewBox="-70 0 460 300">${grid}${axes}
    <polygon points="${vals}" fill="rgba(248,81,73,.18)" stroke="var(--red)" stroke-width="1.5"/>${dots}</svg></div>`;
}

function confMeter(pct) {
  const [label] = confLabel(pct);
  return `<div class="conf-meter">${["MINIMAL", "LOW", "MEDIUM", "HIGH"].map((l) =>
    `<span class="${l === label ? "on" : ""}" style="background:${confColor(l)}"></span>`).join("")}</div>`;
}

/* ── PANELS ──────────────────────────────────────────────────────────── */

const PANELS = {};

PANELS.case = () => `
  ${head("Step 0", "Case", "Describe what you are investigating. Everything is saved automatically once the session has a file.")}
  <div class="split">
    <div class="card">
      <h3>Case details</h3><div class="sub">Shown on every page of the report.</div>
      <div class="grid2">${field("Case ID", "meta.case_id", { ph: "CTI-2026-001" })}${field("Analyst", "meta.analyst", { ph: "Initials" })}</div>
      ${field("IOC under analysis", "meta.ioc", { ph: "IP / domain / hash / URL", mono: true })}
      <label class="f"><span>TLP</span>${seg("meta.tlp", S.K.tlp, "tlp")}</label>
      ${field("Operational / geopolitical context", "meta.geopolitical_context", { area: true, ph: "Why this IOC matters, campaign, sector, region…" })}
    </div>
    <div class="card">
      <h3>How it works</h3><div class="sub">Four techniques from Heuer &amp; Pherson, one after another.</div>
      <div class="alerts">
        <div class="alert info"><b>1 · ACH</b>&nbsp;List every plausible actor, score each piece of evidence against each one. The winner is the hypothesis with the <b>least</b> evidence against it.</div>
        <div class="alert info"><b>2 · KAC</b>&nbsp;Write down what you take for granted. Low-certainty / high-impact assumptions become collection priorities.</div>
        <div class="alert info"><b>3 · I&amp;W</b>&nbsp;Decide in advance what you should observe if a scenario is real, then tick what you actually see.</div>
        <div class="alert info"><b>4 · DA</b>&nbsp;Attack your own conclusion on six fronts. If it does not survive, do not disseminate it.</div>
      </div>
    </div>
  </div>
  ${nextBtn("ach", "Start the ACH")}`;

PANELS.ach = () => {
  const ach = S.session.ach;
  return `
  ${head("Step 1", "Analysis of Competing Hypotheses", "Score evidence against every hypothesis. Look for what <b>refutes</b>, not what confirms.")}
  ${helpBox("How to score", [
    "Add <b>every</b> plausible hypothesis, including “unknown actor” or “benign”. You need at least 2.",
    "Add all evidence, including the <b>absence</b> of something you expected.",
    "For each cell ask: <i>if this hypothesis were true, how likely is this evidence?</i> CC = very consistent … II = very inconsistent.",
    "Source reliability weighs each item (A=1.0, B=0.8, C=0.6, D=0.4): one unconfirmed report cannot eliminate a hypothesis on its own.",
    "Evidence that is consistent with every hypothesis has no diagnostic value and is flagged.",
  ])}
  <div class="grid2">
    <div class="card">
      <h3>Hypotheses <span class="badge">${ach.hypotheses.length}</span></h3><div class="sub">Who or what could explain the activity?</div>
      ${ach.hypotheses.map((h, i) => `<div class="row hyp-row"><span class="tag">H${i + 1}</span>
        ${field("", `ach.hypotheses.${i}.label`, { ph: "Label (e.g. APT40)" })}
        ${field("", `ach.hypotheses.${i}.description`, { ph: "Short description" })}
        <button class="icon" data-action="del-hyp" data-i="${i}" title="Remove">✕</button></div>`).join("")}
      <button class="btn add" data-action="add-hyp">+ Add hypothesis</button>
    </div>
    <div class="card">
      <h3>Evidence <span class="badge">${ach.evidence.length}</span></h3><div class="sub">Facts, observations, and meaningful absences.</div>
      ${ach.evidence.map((e, i) => `<div class="row ev-row"><span class="tag">E${i + 1}</span>
        ${field("", `ach.evidence.${i}.description`, { ph: "What was observed" })}
        <select data-path="ach.evidence.${i}.reliability">${Object.entries(S.K.reliability).map(([k, r]) =>
          `<option value="${k}" ${e.reliability === k ? "selected" : ""} title="${r.label}">${k}</option>`).join("")}</select>
        ${field("", `ach.evidence.${i}.source`, { ph: "Source (Shodan, VT…)" })}
        <button class="icon" data-action="del-ev" data-i="${i}" title="Remove">✕</button></div>`).join("")}
      <button class="btn add" data-action="add-ev">+ Add evidence</button>
    </div>
  </div>
  <div class="card">
    <h3>Consistency matrix</h3><div class="sub">Click a cell to score it. Diagnostic and fragile evidence are flagged live.</div>
    ${live("matrix", achMatrix)}
  </div>
  <div class="split">
    <div class="card"><h3>Result</h3><div class="sub">Computed live from the matrix.</div>${live("achResult", achResult)}</div>
    <div class="card"><h3>Your conclusion</h3><div class="sub">The matrix informs, you decide and justify.</div>${achConclusion()}</div>
  </div>
  ${nextBtn("kac", "Check assumptions")}`;
};

function achMatrix() {
  const ach = S.session.ach, a = S.analysis.ach;
  if (ach.hypotheses.length < 2 || !ach.evidence.length)
    return `<div class="empty">Add at least <b>2 hypotheses</b> and <b>1 evidence item</b> to build the matrix.</div>`;
  const diag = { high: ["green", "diagnostic"], medium: ["gold", "partly diagnostic"], weak: ["", "same everywhere"], none: ["", "no value"] };
  const opts = Object.entries(S.K.consistency);
  return `<div class="matrix-wrap"><table class="matrix"><thead><tr><th class="ev">Evidence</th>
    ${ach.hypotheses.map((h, i) => `<th class="${a.leader === i ? "lead" : ""}" title="${esc(h.description)}">H${i + 1}<span class="hl">${esc(h.label || "-")}</span></th>`).join("")}
    </tr></thead><tbody>
    ${ach.evidence.map((e, ei) => {
      const d = a.evidence[ei] || {};
      const [dc, dl] = diag[d.diagnosticity] || ["", ""];
      return `<tr class="${d.fragile ? "fragile" : ""}"><td class="ev"><span class="tag">E${ei + 1}</span>${esc(e.description || "-")}
        <span class="meta">${e.reliability} · ${esc(e.source || "no source")} · <span class="badge ${dc}">${dl}</span>${d.fragile ? ' <span class="badge orange">fragile</span>' : ""}</span></td>
        ${ach.hypotheses.map((_, hi) => {
          const v = ach.matrix[`${ei}_${hi}`] || "N";
          return `<td><select class="cell v-${v}" data-cell="${ei}_${hi}" title="E${ei + 1} × H${hi + 1}">
            ${opts.map(([k, c]) => `<option value="${k}" ${k === v ? "selected" : ""}>${k}</option>`).join("")}</select></td>`;
        }).join("")}</tr>`;
    }).join("")}
    </tbody></table></div>
    <div class="legend">${opts.map(([k, c]) => `<span><i class="v-${k}" style="background:${{ CC: "rgba(63,185,80,.6)", C: "rgba(63,185,80,.3)", N: "var(--line)", I: "rgba(227,134,59,.5)", II: "rgba(248,81,73,.6)" }[k]}"></i><b>${k}</b> ${c.label}</span>`).join("")}</div>`;
}

function achResult() {
  const a = S.analysis.ach;
  if (!a.ready) return `<div class="empty">Waiting for hypotheses and evidence.</div>`;
  const lead = S.session.ach.hypotheses[a.leader];
  const alerts = [];
  if (a.unscored.length) alerts.push(["warn", `<b>Untested:</b> ${a.unscored.map((i) => "H" + (i + 1)).join(", ")} only has neutral scores, so it cannot win until you score it.`]);
  if (a.tie) alerts.push(["warn", "<b>Tie</b> between the top hypotheses. Add more diagnostic evidence."]);
  if (a.fragile.length) alerts.push(["bad", `<b>Fragile conclusion.</b> Removing ${a.fragile.map((i) => "E" + (i + 1)).join(", ")} changes the leader. Validate these first.`]);
  else alerts.push(["ok", "<b>Robust.</b> No single evidence item changes the leader."]);
  const weak = S.analysis.ach.evidence.filter((e) => e.diagnosticity === "weak" || e.diagnosticity === "none");
  if (weak.length) alerts.push(["info", `${weak.map((e) => "E" + (e.index + 1)).join(", ")} ${weak.length > 1 ? "do" : "does"} not discriminate between hypotheses.`]);
  const chosen = S.session.ach.conclusion.leading_hypothesis;
  if (chosen != null && chosen !== a.leader) alerts.push(["warn", `You chose <b>H${chosen + 1}</b> but the matrix favours <b>H${a.leader + 1}</b>. Explain why in your rationale.`]);
  return `<div class="verdict"><div class="kicker">Matrix leader</div>
      <div class="big"><span class="h">H${a.leader + 1}</span> ${esc(lead.label)}</div>
      <div style="color:var(--muted)">${esc(lead.description)}</div></div>
    <div style="margin-top:16px">${achChart()}</div>
    <div class="alerts">${alerts.map(([k, t]) => `<div class="alert ${k}">${t}</div>`).join("")}</div>`;
}

function achConclusion() {
  const ach = S.session.ach, c = ach.conclusion;
  const a = S.analysis.ach;
  const opts = ach.hypotheses.map((h, i) => `<option value="${i}" ${c.leading_hypothesis === i ? "selected" : ""}>${esc(hName(i))}${a.leader === i ? "  (matrix leader)" : ""}</option>`).join("");
  const suggested = a.ready ? (a.hypotheses.find((r) => r.index === (c.leading_hypothesis ?? a.leader)) || {}).support_pct : null;
  const pct = c.confidence_pct;
  return `
    <label class="f"><span>Leading hypothesis</span>
      <select data-path="ach.conclusion.leading_hypothesis" data-type="int-or-null" data-rerender>
        <option value="" ${c.leading_hypothesis == null ? "selected" : ""}>- choose -</option>${opts}</select></label>
    <label class="f"><span>Confidence</span>
      ${live("confValue", () => {
        const p = S.session.ach.conclusion.confidence_pct;
        const [l, d] = confLabel(p);
        return p == null
          ? `<div style="color:var(--muted);font-size:13px">Not set${suggested != null ? ` (matrix suggests ~${suggested}%)` : ""}. Move the slider.</div>`
          : `<div><b style="color:${confColor(l)};font-size:18px">${l}</b> <span style="color:var(--muted)">${p}% · ${d}</span></div>${confMeter(p)}`;
      })}
      <input type="range" min="0" max="100" value="${pct ?? suggested ?? 50}" data-path="ach.conclusion.confidence_pct" data-type="int"></label>
    ${field("Rationale", "ach.conclusion.rationale", { area: true, ph: "Why this hypothesis? Which diagnostic evidence?" })}
    ${field("Caveats", "ach.conclusion.caveats", { area: true, rows: 2, ph: "What would change this conclusion?" })}
    <label class="f"><span>New evidence that would <b style="color:var(--green)">confirm</b> it</span>${strList("ach.conclusion.confirm_indicators", "e.g. C2 callback to known infrastructure")}</label>
    <label class="f"><span>New evidence that would <b style="color:var(--red)">refute</b> it</span>${strList("ach.conclusion.refute_indicators", "e.g. owner confirms legitimate use")}</label>`;
}

PANELS.kac = () => {
  const A = S.session.kac.assumptions;
  return `
  ${head("Step 2", "Key Assumptions Check", "What are you taking for granted? Rate each assumption. Low certainty with high impact is where your analysis can break.")}
  ${helpBox("Typical CTI assumptions", [
    "The IP / domain is controlled by the adversary (not shared hosting, not a compromised third party).",
    "The campaign is still active, not historical.",
    "Passive DNS / WHOIS / certificate ownership data is accurate.",
    "The vendor report you anchored on is correct.",
    "For each one, write what would prove it wrong, that becomes your next collection task.",
  ])}
  <div class="split">
    <div class="card"><h3>Assumptions <span class="badge">${A.length}</span></h3><div class="sub">Certainty: how sure are you? · Impact: how much does the conclusion change if it is wrong?</div>
      ${A.map((a, i) => `<div class="kac-item"><span class="tag" style="font-family:var(--mono);color:var(--gold);font-weight:600">A${i + 1}</span>
        <div>${field("", `kac.assumptions.${i}.text`, { area: true, rows: 2, ph: "We assume that…" })}
          <div class="controls">${rangeRow("Certainty", `kac.assumptions.${i}.certainty`, 1, 5)}${rangeRow("Impact", `kac.assumptions.${i}.impact`, 1, 5)}</div>
          <div style="margin-top:8px">${field("", `kac.assumptions.${i}.challenge`, { ph: "What would prove this wrong?" })}</div></div>
        <button class="icon" data-action="del-item" data-path="kac.assumptions" data-i="${i}" title="Remove">✕</button></div>`).join("")}
      <button class="btn add" data-action="add-assumption">+ Add assumption</button>
    </div>
    <div>
      <div class="card"><h3>Risk matrix</h3><div class="sub">Top-left red zone = uncertain and high-impact. Red dots are critical assumptions.</div>${live("kacChart", kacChart)}</div>
      <div class="card"><h3>Critical assumptions</h3>${live("kacCrit", () => {
        const crit = S.analysis.kac.critical;
        if (!A.length) return `<div class="empty">No assumptions yet.</div>`;
        if (!crit.length) return `<div class="alert ok">No critical assumption. None is both uncertain (≤2) and high-impact (≥4).</div>`;
        return `<div class="alerts">${crit.map((i) => `<div class="alert bad"><div><b>A${i + 1}</b> ${esc(A[i].text)}<br><span style="opacity:.8">→ Collect: ${esc(A[i].challenge || "define a challenge")}</span></div></div>`).join("")}</div>`;
      })}</div>
    </div>
  </div>
  ${nextBtn("iw", "Define indicators")}`;
};

PANELS.iw = () => {
  const SC = S.session.iw.scenarios;
  return `
  ${head("Step 3", "Indicators & Warnings", "For each scenario, decide in advance what you would observe if it were real. Then mark what you actually saw.")}
  ${helpBox("Tips", [
    "<b style='color:var(--green)'>CONFIRM</b>: observable if the scenario is active. <b style='color:var(--red)'>REFUTE</b>: observable if it is not. <b style='color:var(--blue)'>MONITOR</b>: ambiguous, keep watching.",
    "Map indicators to an ATT&amp;CK technique and a data source: they become your hunting queries.",
    "A confirm indicator marked <b>NO</b> is evidence too (expected but absent).",
    "Any observed refuting indicator caps the assessment.",
  ])}
  ${SC.length ? "" : `<div class="empty" style="margin-bottom:18px">No scenario yet.</div>`}
  ${SC.map((sc, si) => `<div class="scenario">
    <div class="scenario-head"><span class="tag" style="font-family:var(--mono);color:var(--gold);font-weight:700">S${si + 1}</span>
      <div style="flex:1">${field("", `iw.scenarios.${si}.label`, { ph: "Scenario (e.g. APT40 targeting telecom edge devices)" })}</div>
      ${live(`iwGauge${si}`, () => iwGauge(si))}
      <button class="icon" data-action="del-item" data-path="iw.scenarios" data-i="${si}" title="Remove scenario">✕</button></div>
    <div class="scenario-body">
      ${sc.indicators.length ? `<div class="ind-row ind-head"><span>Type</span><span>Indicator</span><span>ATT&amp;CK</span><span>Source</span><span>Observed</span><span></span></div>` : ""}
      ${sc.indicators.map((ind, ii) => {
        const p = `iw.scenarios.${si}.indicators.${ii}`;
        return `<div class="ind-row">
          <select data-path="${p}.type" class="type-${ind.type}" data-rerender>${["CONFIRM", "REFUTE", "MONITOR"].map((t) => `<option ${t === ind.type ? "selected" : ""}>${t}</option>`).join("")}</select>
          ${field("", `${p}.text`, { ph: "Observable" })}
          ${field("", `${p}.mitre`, { ph: "T1190", mono: true })}
          ${field("", `${p}.source`, { ph: "Shodan / SIEM" })}
          ${seg(`${p}.observed`, ["YES", "NO", "UNKNOWN"], "obs", ["Yes", "No", "?"])}
          <button class="icon" data-action="del-item" data-path="iw.scenarios.${si}.indicators" data-i="${ii}" title="Remove">✕</button>
          ${ind.observed === "YES" ? `<div class="note">${field("", `${p}.observation_note`, { ph: "Where / when observed (evidence reference)" })}</div>` : ""}
        </div>`;
      }).join("")}
      <div style="display:flex;gap:8px;margin-top:8px">${["CONFIRM", "REFUTE", "MONITOR"].map((t) =>
        `<button class="btn small" data-action="add-ind" data-si="${si}" data-type="${t}">+ ${t.toLowerCase()}</button>`).join("")}</div>
    </div></div>`).join("")}
  <button class="btn add" data-action="add-scenario">+ Add scenario</button>
  ${nextBtn("da", "Challenge the conclusion")}`;
};

function iwGauge(si) {
  const r = S.analysis.iw.scenarios[si];
  if (!r) return "";
  const cls = { REFUTED: "red", ACTIVE: "green", LIKELY: "gold", WATCH: "orange" }[r.status] || "";
  return `<div style="display:flex;align-items:center;gap:12px">${gauge(r.pct, r.label, r.status, 90)}
    <div style="font-size:12px;color:var(--muted);min-width:130px"><span class="badge ${cls}">${r.status}</span><br>
    confirm ${r.confirm_observed}/${r.confirm_total} · refute ${r.refute_observed}<br>absent ${r.confirm_missing}</div></div>`;
}

PANELS.da = () => {
  const da = S.session.da;
  const fa = finalText();
  return `
  ${head("Step 4", "Devil's Advocacy", "Argue as hard as you can <b>against</b> your own conclusion. Rate how strong each counter-argument really is.")}
  ${helpBox("Why it matters", [
    "State actors deliberately reuse other groups' TTPs. TTP compatibility is not attribution.",
    "Counter-arguments rated 4–5 are reported as unresolved challenges.",
    "If three or more are strong, the conclusion should not be disseminated as-is.",
  ])}
  <div class="card"><div class="grid2">
    <label class="f"><span>Hypothesis challenged</span><input data-path="da.leading_hypothesis" value="${esc(da.leading_hypothesis)}" placeholder="${esc(fa || "Your leading hypothesis")}"></label>
    ${field("Best alternative explanation", "da.alternative_hypothesis", { ph: "e.g. criminal actor mimicking APT TTPs" })}
  </div></div>
  <div class="split">
    <div class="card"><h3>Six challenge areas</h3><div class="sub">Leave an area empty if you truly have no argument.</div>
      ${da.challenges.map((ch, i) => `<div class="da-item"><div class="top"><b>${esc(ch.area)}</b>
        <span class="dots">${[1, 2, 3, 4, 5].map((v) => `<button data-action="set" data-path="da.challenges.${i}.strength" data-v="${v}" data-type="int"
          class="${ch.strength >= v ? "on" : ""}" style="${ch.strength >= v ? `background:${v >= 4 ? "var(--red)" : v >= 3 ? "var(--orange)" : "var(--gold)"}` : ""}" title="Strength ${v}/5">${v}</button>`).join("")}</span></div>
        <div class="hint">${esc(ch.hint)}</div>${field("", `da.challenges.${i}.argument`, { area: true, rows: 2, ph: "Your strongest counter-argument" })}</div>`).join("")}
    </div>
    <div>
      <div class="card"><h3>Pressure map</h3><div class="sub">The larger the red area, the weaker the conclusion.</div>${live("radar", radar)}${live("daVerdict", daVerdict)}</div>
      <div class="card"><h3>Outcome</h3>
        <label class="f"><span>Does this change your conclusion?</span>${seg("da.revised", [false, true], "", ["No, it holds", "Yes, revise"])}</label>
        ${da.revised ? `${field("Revised conclusion", "da.new_conclusion", { area: true, rows: 2 })}
          <label class="f"><span>New confidence</span>${live("daConf", () => {
            const p = S.session.da.new_confidence; const [l, d] = confLabel(p);
            return p == null ? `<div style="color:var(--muted);font-size:13px">Not set</div>` : `<b style="color:${confColor(l)}">${l}</b> <span style="color:var(--muted)">${p}% · ${d}</span>${confMeter(p)}`;
          })}<input type="range" min="0" max="100" value="${da.new_confidence ?? 50}" data-path="da.new_confidence" data-type="int"></label>` : ""}
        ${field("Final note for the record", "da.final_note", { area: true, rows: 2 })}
      </div>
    </div>
  </div>
  ${nextBtn("report", "See the report")}`;
};

function daVerdict() {
  const d = S.analysis.da;
  const cls = { "CONCLUSION SURVIVES": "ok", "UNRESOLVED CHALLENGES": "warn", "CONCLUSION DOES NOT HOLD": "bad" }[d.verdict] || "info";
  return `<div class="alert ${cls}" style="margin-top:10px"><div><b>${d.verdict}</b><br>${d.filled}/6 areas argued · average strength ${d.average}/5 · ${d.strong.length} strong</div></div>`;
}

function finalText() {
  const ach = S.session.ach, a = S.analysis.ach;
  const i = ach.conclusion.leading_hypothesis ?? a.leader;
  if (i == null || !ach.hypotheses[i]) return "";
  const h = ach.hypotheses[i];
  return `H${i + 1} ${h.label}${h.description ? ": " + h.description : ""}`;
}

PANELS.report = () => `
  ${head("Result", "Dashboard & report", "Everything in one place. Export as Markdown (MISP notes, tickets) or print to PDF.",
    `<div class="toolbar">
      <a class="btn" href="/api/report.md?download" download>⬇ Markdown</a>
      <button class="btn" data-action="save-report">Save .md in folder</button>
      <a class="btn" href="/api/session.yaml" download>⬇ YAML</a>
      <button class="btn primary" data-action="print">Print / PDF</button></div>`)}
  ${live("dash", dashboard)}
  <div class="card"><h3>Flash report preview</h3><div class="sub">Updated each time you open this tab.</div>
    <iframe class="report-frame" id="reportFrame" src="/api/report.html?t=${Date.now()}"></iframe></div>`;

function dashboard() {
  const s = S.session, a = S.analysis;
  const ach = s.ach, c = ach.conclusion;
  let lead = c.leading_hypothesis ?? a.ach.leader;
  let pct = c.confidence_pct ?? (a.ach.ready ? (a.ach.hypotheses.find((r) => r.index === lead) || {}).support_pct : null);
  let text = lead != null && ach.hypotheses[lead] ? `H${lead + 1} · ${ach.hypotheses[lead].label}` : "No conclusion yet";
  if (s.da.revised) {
    if (s.da.new_conclusion) text = s.da.new_conclusion;
    if (s.da.new_confidence != null) pct = s.da.new_confidence;
  }
  const [l, d] = confLabel(pct);
  const warn = [];
  if (a.ach.ready && a.ach.fragile.length) warn.push(["bad", `Fragile ACH: depends on ${a.ach.fragile.map((i) => "E" + (i + 1)).join(", ")}`]);
  if (a.ach.ready && c.leading_hypothesis != null && c.leading_hypothesis !== a.ach.leader) warn.push(["warn", `Chosen H${c.leading_hypothesis + 1} ≠ matrix leader H${a.ach.leader + 1}`]);
  if (a.kac.critical.length) warn.push(["bad", `${a.kac.critical.length} critical assumption(s): ${a.kac.critical.map((i) => "A" + (i + 1)).join(", ")}`]);
  a.iw.scenarios.forEach((r, i) => r.status === "REFUTED" && warn.push(["warn", `S${i + 1} refuted by an observed indicator`]));
  if (a.da.strong.length) warn.push([a.da.strong.length >= 3 ? "bad" : "warn", `${a.da.strong.length} strong counter-argument(s), ${a.da.verdict.toLowerCase()}`]);
  const missing = Object.entries({ "Case details": a.completion.meta, ACH: a.completion.ach, KAC: a.completion.kac, "I&W": a.completion.iw, DA: a.completion.da }).filter(([, v]) => !v).map(([k]) => k);
  if (missing.length) warn.push(["info", `Not completed yet: ${missing.join(", ")}`]);
  if (!warn.length) warn.push(["ok", "No open issue, ready for dissemination review."]);

  return `<div class="verdict" style="margin-bottom:18px"><div class="kicker">Bottom line${s.da.revised ? " · revised after DA" : ""}</div>
      <div class="big">${esc(text)}</div>
      ${pct != null ? `<div><b style="color:${confColor(l)}">${l} confidence</b> <span style="color:var(--muted)">${pct}% · ${d}</span></div>${confMeter(pct)}` : ""}
      <div class="alerts">${warn.map(([k, t]) => `<div class="alert ${k}">${esc(t)}</div>`).join("")}</div></div>
    <div class="grid3" style="margin-bottom:18px">
      <div class="kpi"><div class="k">Hypotheses / evidence</div><div class="v">${ach.hypotheses.length} / ${ach.evidence.length}</div>
        <div class="d">${a.ach.ready ? (a.ach.robust ? "robust ranking" : "fragile ranking") : "matrix incomplete"}</div></div>
      <div class="kpi"><div class="k">Critical assumptions</div><div class="v" style="color:${a.kac.critical.length ? "var(--red)" : "var(--green)"}">${a.kac.critical.length}</div>
        <div class="d">of ${s.kac.assumptions.length} listed</div></div>
      <div class="kpi"><div class="k">Devil's advocacy</div><div class="v" style="font-size:16px;margin-top:6px">${a.da.verdict}</div>
        <div class="d">avg strength ${a.da.average}/5</div></div>
    </div>
    <div class="grid2">
      <div class="card"><h3>ACH ranking</h3>${a.ach.ready ? achChart() : '<div class="empty">Matrix incomplete</div>'}</div>
      <div class="card"><h3>Scenarios</h3>${s.iw.scenarios.length ? s.iw.scenarios.map((sc, i) =>
        `<div class="row" style="grid-template-columns:1fr auto"><div><b>S${i + 1}</b> ${esc(sc.label)}</div>${iwGauge(i)}</div>`).join("") : '<div class="empty">No scenario</div>'}</div>
    </div>`;
}

/* ── actions ─────────────────────────────────────────────────────────── */

function remapMatrix(dim, removed) {
  const m = {};
  for (const [k, v] of Object.entries(S.session.ach.matrix)) {
    let [ei, hi] = k.split("_").map(Number);
    let idx = dim === "e" ? ei : hi;
    if (idx === removed) continue;
    if (idx > removed) idx--;
    if (dim === "e") ei = idx; else hi = idx;
    m[`${ei}_${hi}`] = v;
  }
  S.session.ach.matrix = m;
}

async function structural(fn) {
  fn();
  await syncNow();
  render();
}

const ACTIONS = {
  goto: (el) => { S.step = el.dataset.step; history.replaceState(null, "", "#" + S.step); render(); },
  set: (el) => structural(() => {
    let v = el.dataset.v;
    if (el.dataset.type === "int") v = parseInt(v, 10);
    if (v === "true") v = true;
    if (v === "false") v = false;
    setPath(el.dataset.path, v);
  }),
  "add-hyp": () => structural(() => S.session.ach.hypotheses.push({ label: "", description: "" })),
  "del-hyp": (el) => structural(() => {
    const i = +el.dataset.i, c = S.session.ach.conclusion;
    S.session.ach.hypotheses.splice(i, 1);
    remapMatrix("h", i);
    if (c.leading_hypothesis === i) c.leading_hypothesis = null;
    else if (c.leading_hypothesis > i) c.leading_hypothesis--;
  }),
  "add-ev": () => structural(() => S.session.ach.evidence.push({ description: "", reliability: "B", source: "" })),
  "del-ev": (el) => structural(() => { const i = +el.dataset.i; S.session.ach.evidence.splice(i, 1); remapMatrix("e", i); }),
  "add-item": (el) => structural(() => getPath(el.dataset.path).push("")),
  "del-item": (el) => {
    const item = getPath(el.dataset.path)[+el.dataset.i];
    const hasContent = item && typeof item === "object"
      && (item.text || item.label || item.argument || (item.indicators || []).length);
    if (hasContent && !confirm("Remove this item?")) return;
    structural(() => getPath(el.dataset.path).splice(+el.dataset.i, 1));
  },
  "add-assumption": () => structural(() => S.session.kac.assumptions.push({ text: "", certainty: 3, impact: 3, challenge: "" })),
  "add-scenario": () => structural(() => S.session.iw.scenarios.push({ label: "", indicators: [] })),
  "add-ind": (el) => structural(() => S.session.iw.scenarios[+el.dataset.si].indicators.push(
    { text: "", type: el.dataset.type, mitre: "", source: "", observed: "UNKNOWN", observation_note: "" })),
  save: () => saveSession(),
  new: async () => {
    if (!S.path && !confirm("This session has never been saved. Discard it?")) return;
    load(await api("/api/new", {}));
    S.step = "case"; render();
    toast("New session");
  },
  open: () => openDialog(),
  "close-modal": () => ($("#modal").hidden = true),
  "open-file": async (el) => {
    try { load(await api("/api/open", { name: el.dataset.name })); $("#modal").hidden = true; S.step = "report"; render(); toast("Opened " + el.dataset.name); }
    catch (e) { toast(e.message, true); }
  },
  "save-report": async () => {
    try { const r = await api("/api/report/save", {}); toast("Report saved → " + r.file); } catch (e) { toast(e.message, true); }
  },
  print: () => {
    const w = window.open("/api/report.html", "_blank");
    if (w) w.addEventListener("load", () => w.print());
  },
};

async function saveSession() {
  try {
    let body = {};
    if (!S.path) {
      const cid = (S.session.meta.case_id || "cti").replace(/[^\w.-]+/g, "_");
      const name = prompt("Save session as (in the working folder):", `session_${cid}.yaml`);
      if (!name) return;
      body = { name };
    }
    await syncNow();
    load(await api("/api/save", body));
    toast("Saved → " + S.path);
  } catch (e) { toast(e.message, true); }
}

async function openDialog() {
  $("#modalTitle").textContent = "Open a session";
  $("#modalBody").innerHTML = `<div class="empty">Loading…</div>`;
  $("#modal").hidden = false;
  try {
    const files = await api("/api/files");
    $("#modalBody").innerHTML = (files.length ? files.map((f) => `
      <div class="file" data-action="open-file" data-name="${esc(f.name)}">
        <div><div class="n">${esc(f.name)}</div><div class="m">${esc(f.case_id)} · ${esc(f.ioc)}</div></div>
        <div class="m">${esc((f.updated || "").replace("T", " ").slice(0, 16))}</div></div>`).join("")
      : `<div class="empty">No session file in this folder yet.</div>`) + `
      <div style="margin-top:14px;font-size:13px;color:var(--muted)">Or import a YAML file from elsewhere:</div>
      <input type="file" id="importFile" accept=".yaml,.yml" style="margin-top:6px">`;
    $("#importFile").addEventListener("change", async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      try {
        load(await api("/api/import", { text: await f.text(), name: f.name }));
        $("#modal").hidden = true; S.step = "report"; render();
        toast(S.path ? "Imported " + f.name : "Imported. Click Save to keep it");
      } catch (e) { toast("Import failed: " + e.message, true); }
    });
  } catch (e) { $("#modalBody").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`; }
}

/* ── events ──────────────────────────────────────────────────────────── */

function readValue(el) {
  const t = el.dataset.type;
  if (t === "int") return parseInt(el.value, 10);
  if (t === "int-or-null") return el.value === "" ? null : parseInt(el.value, 10);
  return el.value;
}

document.addEventListener("input", (ev) => {
  const el = ev.target;
  if (!el.dataset || !el.dataset.path || el.tagName === "SELECT") return;
  setPath(el.dataset.path, readValue(el));
  if (el.dataset.echo !== undefined) el.nextElementSibling.textContent = el.value;
  if (el.type === "range") refreshLiveLocal();
  scheduleSync();
});

// Update the parts that only depend on the edited value without waiting for the server
function refreshLiveLocal() {
  ["confValue", "daConf", "kacChart"].forEach((n) => {
    document.querySelectorAll(`[data-live="${n}"]`).forEach((el) => (el.innerHTML = LIVE[n]()));
  });
}

document.addEventListener("change", (ev) => {
  const el = ev.target;
  if (el.dataset && el.dataset.cell) {
    S.session.ach.matrix[el.dataset.cell] = el.value;
    el.className = "cell v-" + el.value;
    syncNow();
    return;
  }
  if (!el.dataset || !el.dataset.path || el.tagName !== "SELECT") return;
  setPath(el.dataset.path, readValue(el));
  if (el.dataset.rerender !== undefined) structural(() => {});
  else scheduleSync();
});

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  if (el.tagName === "A") return;
  ev.preventDefault();
  const fn = ACTIONS[el.dataset.action];
  if (fn) fn(el);
});

document.addEventListener("keydown", (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key === "s") { ev.preventDefault(); saveSession(); }
  if (ev.key === "Escape") $("#modal").hidden = true;
});
$("#modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") $("#modal").hidden = true; });

window.addEventListener("beforeunload", (ev) => {
  if (!S.path && (S.session.meta.ioc || S.session.ach.hypotheses.length)) { ev.preventDefault(); ev.returnValue = ""; }
});

api("/api/state").then((p) => {
  const fromHash = location.hash.slice(1);
  if (STEPS.some((st) => st.id === fromHash)) S.step = fromHash;
  else if (p.path) S.step = "report";
  load(p);
}).catch((e) => toast("Cannot reach CSAT server: " + e.message, true));
