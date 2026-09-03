"use strict";

// ------------------------------------------------------------ state
const app = {
  state: null, boards: null,
  slug: decodeURIComponent(location.pathname.split("/").filter(Boolean)[0] || ""),
  sheet: "board", mode: "list", view: "live", track: "", grep: "",
  selected: null, // {kind: "item"|"peer", id}
  lastReceived: null, paletteIndex: 0, paletteEntries: [],
};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const api = (p) => `/${encodeURIComponent(app.slug)}/${p}`;
const clip = (t, n) => { const v = String(t || "").replace(/\s+/g, " ").trim(); return v.length > n ? v.slice(0, n - 1) + "…" : v; };
const shortTrack = (t) => String(t || "").replace(/^\s*(?:\[[^\]]{1,24}\]\s*)+/, "").replace(/^\s*track\s*:\s*/i, "").replace(/\s*\([^)]*\)\s*$/, "").trim();

const LABEL = { active: "in progress", ready: "ready", waiting: "blocked", decision: "decision", dream: "dream", done: "done", track: "track" };
const label = (s) => LABEL[s] || String(s || "").replaceAll("_", " ");
const ATTN = { "needs-user": "needs you", failed: "failed", working: "working", present: "present", idle: "idle", finished: "finished", ended: "ended", gone: "gone", unseen: "unseen" };
const attn = (a) => ATTN[a] || String(a || "");
const cls = (s) => "c-" + String(s || "faint").replace(/[^a-z-]/g, "");

const fmtDate = (v) => { if (!v) return "—"; const d = new Date(v); return Number.isNaN(d.valueOf()) ? v : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d); };
const ago = (v) => { if (!v) return "never"; const d = new Date(v); if (Number.isNaN(d.valueOf())) return v; const m = Math.floor((Date.now() - d.getTime()) / 60000); return m < 1 ? "now" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`; };
const rel = (d) => { if (!d) return "waiting for state"; const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000)); return s < 3 ? "updated now" : s < 60 ? `updated ${s}s ago` : `updated ${Math.floor(s / 60)}m ago`; };

function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("visible"); window.clearTimeout(toast.timer); toast.timer = window.setTimeout(() => t.classList.remove("visible"), 1800); }

// ------------------------------------------------------------ derived
const rowText = (r) => r.digest || r.title;
function matches(r) {
  if (app.answer && !app.answer.pending) return app.answer.cited?.length ? app.answer.cited.includes(r.id) : true;
  if (!app.grep) return true;
  const hay = [r.id, r.title, r.digest, r.track_title, r.claimant?.label, r.description].filter(Boolean).join(" ").toLowerCase();
  return hay.includes(app.grep.toLowerCase());
}
function trackOk(r) { return !app.track || r.track === app.track || (app.track === "(none)" && !r.track); }

// The inbox is asks only: every row is who/what · the ask · the verb you perform.
const VERB_RANK = ["grant", "fix", "rule", "split", "close", "apply", "sync", "fix doc", "read", "launch"];
function inboxRows(s) {
  const out = [];
  for (const p of s.peers || []) {
    if (p.attention === "needs-user") out.push({ kind: "peer", color: "needs-user", text: `${p.alias || p.agent_id} · ${p.pulse?.latest_prompt ? "“" + clip(p.pulse.latest_prompt, 90) + "”" : p.goal || "waiting on you"}`, verb: "grant", target: { kind: "peer", id: p.agent_id } });
    if (p.attention === "failed") out.push({ kind: "peer", color: "failed", text: `${p.alias || p.agent_id} · ${p.goal || "failed"}`, verb: "fix", target: { kind: "peer", id: p.agent_id } });
  }
  for (const r of s.decisions || []) out.push({ kind: "decision", color: "decision", text: rowText(r), verb: "rule", target: { kind: "item", id: r.id } });
  for (const c of (s.coord?.contention || [])) out.push({ kind: "contention", color: "waiting", text: `${c.paths.join(", ")} · ${c.owners.join(" and ")}`, verb: "split", target: { kind: "sheet", id: "coord" } });
  const findings = s.drift?.findings || [];
  const byId = new Map((s.all || []).map((r) => [r.id, r]));
  for (const f of findings) {
    if (f.kind === "landed_open" && f.issue_id) out.push({ kind: "landed", color: "decision", text: `${rowText(byId.get(f.issue_id) || { title: f.issue_id })} · landed in ${f.evidence || "a commit"}, still open`, verb: "close", target: { kind: "item", id: f.issue_id }, act: { action: "close", id: f.issue_id } });
    else if (f.kind === "stale_dream" && f.issue_id) out.push({ kind: "dream", color: "dream", text: `${rowText(byId.get(f.issue_id) || { title: f.issue_id })} · parked since ${f.evidence?.replace(/^created_at /, "") || "a while"}`, verb: "rule", target: { kind: "item", id: f.issue_id }, act: { action: "rule", id: f.issue_id } });
    else if (f.kind === "doc_reference") out.push({ kind: "doc", color: "muted", text: `${f.detail || "a document names a missing item"} · ${f.evidence || ""}`, verb: "fix doc", target: { kind: "sheet", id: "debug" } });
  }
  const behind = findings.filter((f) => f.kind === "handoff_presentation").length;
  if (behind) out.push({ kind: "handoffs", color: "muted", text: `${behind} work-order filename${behind === 1 ? "" : "s"} behind their priority`, verb: "sync", target: { kind: "sheet", id: "debug" }, act: { action: "sync" } });
  const safe = findings.filter((f) => /dead claim|resolved blocker|recompute status|remove resolved/i.test(`${f.kind} ${f.detail} ${f.proposed_fix}`)).length;
  if (safe) out.push({ kind: "repairs", color: "muted", text: `${safe} safe repair${safe === 1 ? "" : "s"} (dead claims, resolved blockers)`, verb: "apply", target: { kind: "sheet", id: "debug" }, act: { action: "fix" } });
  for (const d of (s.coord?.drops || [])) out.push({ kind: "drop", color: "muted", text: `${Array.isArray(d.path) ? d.path.join(", ") : d.path || "note"} · ${clip(d.note || "", 80)} · from ${d.owner}`, verb: "read", target: { kind: "sheet", id: "coord" } });
  const first = (s.next || [])[0];
  if (first) out.push({ kind: "ready", color: "ready", text: `${rowText(first)} · priority #${(first.order ?? 0) + 1}`, verb: "launch", target: { kind: "item", id: first.id } });
  out.sort((a, b) => VERB_RANK.indexOf(a.verb) - VERB_RANK.indexOf(b.verb));
  return out.filter((x) => !app.grep || x.text.toLowerCase().includes(app.grep.toLowerCase()));
}

function relationStateClass(state) {
  return ({ resolved: "c-done", unavailable: "c-muted", missing: "c-waiting", ambiguous: "c-decision" }[state] || "c-muted");
}
function relationMarkup(rows) {
  if (!rows?.length) return "";
  return `<div class="relation-list"><p class="relation-heading">RELATIONS</p>${rows.map((relation) => {
    const resolution = relation.resolution;
    const state = resolution?.state || "declared";
    const target = resolution?.issue;
    const reciprocity = relation.reciprocity ? ` · reciprocity ${esc(String(relation.reciprocity).replaceAll("_", " "))}` : "";
    const detail = target
      ? `<span class="relation-target">${esc(target.title)} · ${esc(target.status)}</span>`
      : resolution?.detail ? `<span class="relation-target">${esc(resolution.detail)}</span>` : "";
    return `<p class="relation-line">
      <span class="label">${esc(String(relation.kind).replaceAll("_", " "))}</span>
      <strong><code>${esc(relation.hint || relation.to)}</code> <span class="${esc(relationStateClass(state))}">${esc(state)}</span>${reciprocity}${detail}<span class="faint relation-uri">${esc(relation.to)}</span></strong>
    </p>`;
  }).join("")}</div>`;
}

// ------------------------------------------------------------ acting
// A click runs one manna verb through the daemon's own identity. Nothing else
// on this page writes. Delete asks for a second click; refusals print verbatim.
const acts = new Map(); // "action:id" -> {pending, ok, note, armed}
function actNote(result) {
  if (result.ok) return result.action === "close" ? "closed" : result.action === "sync" ? "synced" : result.action === "fix" ? "applied" : result.action === "promote" ? "promoted to item" : "deleted";
  const step = (result.steps || []).find((x) => x.code !== 0);
  const text = (step && (step.stderr || step.stdout).trim().split("\n").slice(-1)[0]) || result.error || "refused";
  return `refused: ${text}`;
}
async function act(action, id, confirm) {
  const key = `${action}:${id || ""}`;
  acts.set(key, { pending: true }); renderInbox(app.state);
  try {
    const r = await fetch(api("api/act"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, id: id || null, confirm: !!confirm, token: app.state?.act_token }) });
    const d = await r.json();
    acts.set(key, { pending: false, ok: !!d.ok, note: actNote({ ...d, action }) });
    toast(actNote({ ...d, action }));
  } catch (e) { acts.set(key, { pending: false, ok: false, note: "refused: request failed" }); }
  renderInbox(app.state);
  fetchState();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const action = b.dataset.act, id = b.dataset.actId || null;
  if (action === "delete") {
    const key = `rule:${id}`; const st = acts.get(key) || {};
    if (st.armed !== "delete") { acts.set(key, { ...st, armed: "delete" }); renderInbox(app.state); window.setTimeout(() => { const cur = acts.get(key); if (cur?.armed === "delete") { acts.set(key, { ...cur, armed: null }); renderInbox(app.state); } }, 4000); return; }
    acts.set(key, { armed: null }); act("delete", id, true); return;
  }
  act(action, id, false);
}, true);

// ------------------------------------------------------------ rendering: rows
function itemRow(r, opts) {
  const sel = app.selected?.kind === "item" && app.selected.id === r.id;
  const st = r.effective;
  const needs = st === "active" && r.claimant?.attention === "needs-user";
  const statePlain = st === "waiting" && r.blockers?.length ? `blocked · ${r.blockers.map((b) => b.id.replace(/^mn-/, "")).join(", ")}` : needs ? "needs you" : label(st);
  const stateText = st === "waiting" && r.blockers?.length ? `blocked · <span class="keep-case">${esc(r.blockers.map((b) => b.id.replace(/^mn-/, "")).join(", "))}</span>` : esc(needs ? "needs you" : label(st));
  const last = opts?.age ? esc(ago(r.updated_at)) : r.order != null ? `#${r.order + 1}` : "";
  return `<div class="row ${needs ? "s-needs-user" : "s-" + esc(st)}${sel ? " selected" : ""}" data-item="${esc(r.id)}" role="button" tabindex="0">
    <span class="id">${esc(r.id)}</span>
    <span class="digest${r.digest ? "" : " fallback"}" title="${esc(r.title)}">${esc(rowText(r))}</span>
    <span class="track" title="${esc(r.track_title || "")}">${esc(shortTrack(r.track_title))}</span>
    <span class="pill ${needs ? "c-needs-user" : cls(st)}" title="${esc(statePlain)}">${stateText}</span>
    <span class="prio">${last}</span>
  </div>`;
}
function section(lbl, rows, empty, opts) {
  return `<div class="sheet-head"><span class="prompt">manna ${esc(lbl)}</span><span class="count">${rows.length}</span></div><div class="list">${rows.length ? rows.map((r) => itemRow(r, opts)).join("") : `<p class="empty">${esc(empty)}</p>`}</div>`;
}
function renderBoard(s) {
  const el = $("#board-list");
  if (app.mode === "timeline") { el.innerHTML = renderTimeline(s); return; }
  const f = (rows) => rows.filter((r) => trackOk(r) && matches(r));
  let html = "";
  if (app.answer && !app.answer.pending && app.answer.cited?.length) {
    const byId = new Map((s.all || []).map((r) => [r.id, r]));
    const cited = app.answer.cited.map((id) => byId.get(id)).filter(Boolean);
    html += section("cited", cited, "the answer cites nothing on this board");
  }
  const v = app.view;
  const waiting = [];
  for (const w of s.waves || []) for (const r of w.items) waiting.push(r);
  for (const r of s.unlayered || []) waiting.push(r);
  // a section view (now · next · waiting, from an estate link) shows that section alone
  if (v === "live" || v === "all" || v === "now") html += section("now", f(s.now || []), "nothing claimed");
  if (v === "live" || v === "all" || v === "next") html += section("next", f(s.next || []), "nothing is ready");
  if (v === "live" || v === "all" || v === "waiting") html += section("waiting", f(waiting), "nothing is blocked");
  if (v === "dreams" || v === "all") html += section("dreams", f(s.dreams || []), "no dreams parked");
  if (v === "done" || v === "all") {
    const done = (s.all || []).filter((r) => r.effective === "done").sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    html += section("done", f(done), "nothing done yet");
  }
  if (v === "recent") {
    const recent = (s.all || []).slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    html += section("recent", f(recent), "board is empty", { age: true });
  }
  el.innerHTML = colsHeader("board", v === "recent" ? { "#": "age" } : null) + html;
  fitColumns($("#sheet-board"), "board");
}
function renderTimeline(s) {
  const f = (rows) => rows.filter((r) => trackOk(r) && matches(r));
  const lane = (lbl, colorCls, rows) => rows.length ? `<div class="tl ${colorCls}"><span class="lbl">${esc(lbl)}</span><span class="bar"></span><div class="items">${rows.map((r) => `<span class="item${app.selected?.kind === "item" && app.selected.id === r.id ? " selected" : ""}" data-item="${esc(r.id)}" title="${esc(r.title)}"><span class="id">${esc(r.id)}</span>${esc(clip(rowText(r), 60))}${r.blockers?.length ? ` <span class="faint">← ${esc(r.blockers.map((b) => b.id.replace(/^mn-/, "")).join(", "))}</span>` : ""}</span>`).join("")}</div></div>` : "";
  let html = `<div class="sheet-head"><span class="prompt">manna timeline</span></div>`;
  const v = app.view;
  if (v === "live" || v === "all" || v === "now") html += lane("now", "c-active", f(s.now || []));
  if (v === "live" || v === "all" || v === "next") html += lane("ready", "c-ready", f(s.next || []));
  if (v === "live" || v === "all" || v === "waiting") {
    for (const w of s.waves || []) html += lane(`wave ${w.wave}`, "c-waiting", f(w.items));
    if ((s.unlayered || []).length) html += lane("unlayered", "c-faint", f(s.unlayered));
  }
  if (v === "dreams" || v === "all") html += lane("dreams", "c-dream", f(s.dreams || []));
  if (v === "done" || v === "all") html += lane("done", "c-faint", f((s.all || []).filter((r) => r.effective === "done")));
  if (v === "recent") html += lane("recent", "c-ready", f((s.all || []).slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))));
  return html;
}
function renderInbox(s) {
  const rows = inboxRows(s);
  $("#inbox-cap").textContent = String(rows.length);
  $("#inbox-list").innerHTML = colsHeader("inbox") + (rows.length ? rows.map((x, i) => {
    const key = x.act ? `${x.act.action}:${x.act.id || ""}` : "";
    const ruleState = x.act?.action === "rule" ? (acts.get(`promote:${x.act.id}`) || acts.get(`delete:${x.act.id}`)) : null;
    const st = key ? (acts.get(key) || ruleState) : null;
    let verbCell;
    if (!x.act) verbCell = `<span class="pill verb ${cls(x.color)}">${esc(x.verb)}</span>`;
    else if (st?.pending) verbCell = `<span class="pill verb c-muted">working…</span>`;
    else if (x.act.action === "rule") verbCell = `<span class="verb-group"><button type="button" class="pill verb c-ready" data-act="promote" data-act-id="${esc(x.act.id)}">promote</button><button type="button" class="pill verb c-waiting" data-act="delete" data-act-id="${esc(x.act.id)}">${st?.armed === "delete" ? "delete · confirm" : "delete"}</button></span>`;
    else verbCell = `<button type="button" class="pill verb ${cls(x.color)}" data-act="${esc(x.act.action)}" data-act-id="${esc(x.act.id || "")}">${esc(x.verb)}</button>`;
    const note = st && !st.pending && st.note ? `<span class="act-note ${st.ok ? "c-done" : "c-waiting"}">${esc(st.note)}</span>` : "";
    return `<div class="row inbox s-${esc(x.color)}" data-target-kind="${esc(x.target.kind)}" data-target-id="${esc(x.target.id)}" role="button" tabindex="0">
      <span class="kind">${esc(x.kind)}</span><span class="text">${esc(x.text)}${note}</span>${verbCell}
    </div>`;
  }).join("") : `<p class="empty">Nothing is waiting on you.</p>`);
  fitColumns($("#sheet-inbox"), "inbox");
}
function peerRow(p) {
  const sel = app.selected?.kind === "peer" && app.selected.id === p.agent_id;
  const what = p.goal || (p.pulse?.latest_prompt ? "“" + clip(p.pulse.latest_prompt, 100) + "”" : "");
  const holding = (p.holding || []).map((h) => `<a href="#item/${esc(h.id)}" data-item="${esc(h.id)}">${esc(h.id)}</a>`).join(" ");
  return `<div class="row peer s-${esc(p.attention)}${sel ? " selected" : ""}" data-peer="${esc(p.agent_id)}" role="button" tabindex="0">
    <span class="id" title="${esc(p.agent_id)}">${esc(p.alias || p.agent_id)}</span>
    <span class="text">${what ? esc(what) : '<span class="faint">no focus declared</span>'}${p.pulse?.activity ? `<span class="sub">${esc(p.pulse.activity)}</span>` : ""}</span>
    <span class="track">${holding}</span>
    <span class="pill ${cls(p.attention)}">${esc(attn(p.attention))}</span>
    <span class="age">${esc(p.age || "")}</span>
  </div>`;
}
function renderCoord(s) {
  // peers === null means coordination has not been read yet (fast payload,
  // cold cache): say so. Zero peers is a different, definite statement.
  if (s.peers == null) {
    const head = (l) => `<div class="sheet-head"><span class="prompt">coord ${esc(l)}</span><span class="count">…</span></div>`;
    const reading = '<div class="list"><p class="empty">still reading coordination…</p></div>';
    $("#coord-list").innerHTML = head("needs you") + reading + head("peers") + reading + head("claims") + reading + head("drops") + reading;
    return;
  }
  const peers = (s.peers || []).filter((p) => !app.grep || [p.agent_id, p.alias, p.goal, p.pulse?.latest_prompt].filter(Boolean).join(" ").toLowerCase().includes(app.grep.toLowerCase()));
  const needs = peers.filter((p) => p.attention === "needs-user" || p.attention === "failed");
  const here = peers.filter((p) => p.attention !== "gone" && !needs.includes(p));
  const gone = peers.filter((p) => p.attention === "gone");
  const c = s.coord || { claims: [], contention: [], drops: [] };
  const head = (l, n) => `<div class="sheet-head"><span class="prompt">coord ${esc(l)}</span><span class="count">${esc(String(n))}</span></div>`;
  let html = head("needs you", needs.length) + `<div class="list">${colsHeader("peer")}${needs.length ? needs.map(peerRow).join("") : '<p class="empty">Nobody is waiting on you.</p>'}</div>`;
  html += head("peers", here.length) + `<div class="list">${colsHeader("peer")}${here.length ? here.map(peerRow).join("") : '<p class="empty">No live sessions.</p>'}</div>`;
  const claims = c.claims.filter((x) => !app.grep || `${x.path} ${x.owner} ${x.reason || ""}`.toLowerCase().includes(app.grep.toLowerCase()));
  html += head("claims", claims.length) + `<div class="list">${colsHeader("claim")}${claims.length ? claims.map((x) => `<div class="row claim ${x.contended ? "s-waiting" : x.stale ? "s-gone" : "s-ready"}">
      <span class="text" title="${esc(x.path)}">${esc(x.path)}${x.reason ? `<span class="sub">${esc(x.reason)}</span>` : ""}</span>
      <span class="id" title="${esc(x.owner)}">${esc(x.owner_alias || x.owner)}</span>
      <span class="pill ${x.contended ? "c-waiting" : x.stale ? "c-faint" : "c-ready"}">${x.contended ? "contended" : x.stale ? `stale · ${esc(x.owner_status || "gone")}` : esc(x.strength || "claimed")}</span>
      <span class="age">${esc(ago(x.updated_at))}</span></div>`).join("") : '<p class="empty">No advisory claims.</p>'}</div>`;
  html += head("drops", c.drops.length) + `<div class="list">${colsHeader("drop")}${c.drops.length ? c.drops.map((d) => `<div class="row drop s-muted">
      <span class="id">${esc(d.owner)} → ${esc(d.for || "any")}</span>
      <span class="text">${esc(Array.isArray(d.path) ? d.path.join(", ") : d.path || "")}${d.note ? `<span class="sub">${esc(d.note)}</span>` : ""}</span>
      <span class="age">${esc(ago(d.created_at))}</span></div>`).join("") : '<p class="empty">No drops waiting.</p>'}</div>`;
  if (gone.length) html += head("gone", gone.length) + `<div class="list">${colsHeader("peer")}${gone.map(peerRow).join("")}</div>`;
  $("#coord-list").innerHTML = html;
  for (const k of ["peer", "claim", "drop"]) fitColumns($("#sheet-coord"), k);
}
function renderDebug(s) {
  const d = s.drift || {};
  const kv = (k, v) => `<span>${esc(k)}</span><b>${v}</b>`;
  let html = `<div class="sheet-head"><span class="prompt">manna debug</span></div>`;
  html += `<div class="kv">
    ${kv("drift", d.source === "reconcile" ? `${d.count} live · ${Object.entries(d.kinds || {}).map(([k, n]) => `${esc(k)} ${n}`).join(", ") || "clean"}` : `${d.count ?? 0} from file`)}
    ${kv("drift file", d.file?.present ? `${d.file.count} findings · written ${esc(ago(d.file.generated_at))} ago` : "no drift.yaml written yet")}
    ${kv("board", `${s.total} rows · workflow ${esc(s.board?.workflow || "unknown")}${s.board?.board_id ? ` · ${esc(s.board.board_id)}` : ""} · ${s.board?.order_count} in handoff order · issues written ${esc(ago(s.board?.issues_modified_at))} ago`)}
    ${kv("repo", s.git?.is_repo ? `${esc(s.git.branch || "(detached)")} / HEAD ${esc(s.git.head)} / ${s.git.dirty_paths} dirty` : "not a git repository")}
    ${kv("coord", s.peers == null ? "still reading" : `presence ${esc(s.coord_refreshed_ago)}s old · ${s.peers.length} rows`)}
    ${kv("digests", `${s.digests?.ready ?? 0} ready · ${s.digests?.missing ?? 0} missing${s.digests?.generating ? " · generating" : ""}${s.digests?.model ? ` · ${esc(s.digests.model)}` : ""}`)}
    ${kv("root", esc(s.root))}
    ${kv("markers", (s.board?.decision_markers || []).map(esc).join(" "))}
  </div>`;
  const rows = (d.findings || []).filter((f) => !app.grep || JSON.stringify(f).toLowerCase().includes(app.grep.toLowerCase()));
  html += `<div class="sheet-head"><span class="prompt">manna reconcile</span><span class="count">${rows.length}</span></div><div class="list">${colsHeader("finding")}`;
  html += rows.length ? rows.map((f) => `<div class="row finding s-decision"><span class="kind">${esc(f.kind)}</span><span class="id">${f.issue_id ? `<a href="#item/${esc(f.issue_id)}" data-item="${esc(f.issue_id)}">${esc(f.issue_id)}</a>` : ""}</span><span class="text">${esc(f.detail || "")}${f.evidence ? ` <span class="faint">(${esc(f.evidence)})</span>` : ""}${f.proposed_fix ? `<span class="sub">fix: ${esc(f.proposed_fix)}</span>` : ""}</span></div>`).join("") : '<p class="empty">No findings.</p>';
  html += "</div>";
  $("#debug-list").innerHTML = html;
  fitColumns($("#sheet-debug"), "finding");
}

// ------------------------------------------------------------ inspector
// Write the inspector only when its content actually changed: every state
// push re-rendered it wholesale, and a copy button destroyed between a
// press and its release swallows the click entirely — the "worked once,
// then dead" bug. Equal HTML is skipped, so the nodes live on.
function setInspector(el, html) {
  if (el.__lastHtml === html) return;
  el.__lastHtml = html;
  el.innerHTML = html;
}
function renderInspector(s) {
  const el = $("#inspector");
  const sel = app.selected;
  if (!sel) { setInspector(el, '<p class="empty">select a row · ⌘K to ask</p>'); return; }
  if (sel.kind === "peer") {
    if (s.peers == null) { setInspector(el, '<p class="empty">still reading coordination…</p>'); return; }
    const p = (s.peers || []).find((x) => x.agent_id === sel.id);
    if (!p) { setInspector(el, '<p class="empty">that session is no longer on the board</p>'); return; }
    const pu = p.pulse || {};
    setInspector(el, `<div class="head"><span class="pill ${cls(p.attention)}">${esc(attn(p.attention))}</span><span>${esc(p.runtime || "")}${p.role ? " · " + esc(p.role) : ""}</span></div>
      <h2>${esc(p.alias || p.agent_id)}</h2>
      ${p.goal ? `<div class="digest-line">${esc(p.goal)}</div>` : ""}
      ${pu.latest_prompt ? `<div class="desc">“${esc(pu.latest_prompt)}”</div>` : ""}
      <div class="meta">
        <span>session</span><b>${esc(p.agent_id)}</b>
        <span>liveness</span><b><span class="${cls(p.status)}">${esc(p.status)}</span> ${esc(p.age || "")}</b>
        ${pu.status ? `<span>pulse</span><b>${esc(pu.status)}${pu.activity ? " · " + esc(pu.activity) : ""}${pu.updated_at ? ` <span class="faint">${esc(ago(pu.updated_at))} ago</span>` : ""}</b>` : ""}
        ${pu.todo?.total ? `<span>todo</span><b>${esc(pu.todo.done)}/${esc(pu.todo.total)}${pu.todo.current ? " · " + esc(pu.todo.current) : ""}</b>` : ""}
        ${(p.holding || []).length ? `<span>holding</span><b>${p.holding.map((h) => `<a href="#item/${esc(h.id)}" data-item="${esc(h.id)}">${esc(h.id)}</a> ${esc(h.title)}`).join("<br>")}</b>` : ""}
        ${(p.paths || []).length ? `<span>paths</span><b>${p.paths.map(esc).join("<br>")}</b>` : ""}
      </div>
      <div class="actions"><span class="muted">copy:</span><button type="button" data-copy="${esc(p.agent_id)}" data-label="session">[session]</button><button type="button" data-copy="agent-do coord pulse show ${esc(p.agent_id)}" data-label="pulse cmd">[pulse cmd]</button></div>`);
    return;
  }
  const r = (s.all || []).find((x) => x.id === sel.id);
  if (!r) { setInspector(el, '<p class="empty">that item is no longer on the board</p>'); return; }
  const summaryKey = itemSummaryKey(r);
  const priorSummary = summaries.get(r.id);
  if (priorSummary && priorSummary.key !== summaryKey) summaries.delete(r.id);
  if (r.summary) summaries.set(r.id, { summary: r.summary, error: null, key: summaryKey });
  const st = r.effective;
  const cl = r.claimant;
  const relations = relationMarkup(r.relations || []);
  setInspector(el, `<div class="head"><span>${esc(r.id)}</span><span class="pill ${cls(st)}">${esc(label(st))}</span>${r.order != null ? `<span>#${r.order + 1}</span>` : ""}${r.kind !== "item" ? `<span>${esc(r.kind)}</span>` : ""}</div>
    <details class="summary" id="summary-block"${summaryOpen() ? " open" : ""}><summary class="tag">AI summary</summary><div class="summary-body">${summaryBody(r.id)}</div></details>
    <h2>${esc(r.title)}</h2>
    ${r.digest ? `<div class="digest-line">${esc(r.digest)}</div>` : ""}
    ${r.description ? `<div class="desc">${esc(r.description)}</div>` : ""}
    <div class="meta">
      <span>track</span><b>${esc(shortTrack(r.track_title) || "—")}</b>
      ${r.created_at ? `<span>filed</span><b>${esc(fmtDate(r.created_at))} <span class="faint">${esc(ago(r.created_at))} ago</span></b>` : ""}
      <span>touched</span><b>${esc(fmtDate(r.updated_at))} <span class="faint">${esc(ago(r.updated_at))} ago</span></b>
      ${r.source ? `<span>source</span><b>${esc(r.source)}</b>` : ""}
      ${cl ? `<span>claimed by</span><b>${esc(cl.label)} <span class="${cls(cl.attention)}">${esc(attn(cl.attention))}</span>${cl.pulse?.activity ? ` · ${esc(cl.pulse.activity)}` : ""}${cl.goal ? `<br><span class="faint">${esc(cl.goal)}</span>` : ""}</b>` : ""}
      ${r.blockers?.length ? `<span>waits on</span><b>${r.blockers.map((b) => `<a href="#item/${esc(b.id)}" data-item="${esc(b.id)}">${esc(b.id)}</a> <span class="${cls(b.status === "blocked" ? "waiting" : b.status)}">${esc(label(b.status))}</span> ${esc(b.title)}`).join("<br>")}</b>` : ""}
      ${r.dependents?.length ? `<span>unblocks</span><b>${r.dependents.map((d) => `<a href="#item/${esc(d)}" data-item="${esc(d)}">${esc(d)}</a>`).join(", ")}</b>` : ""}
      ${r.commits?.length ? `<span>commits</span><b>${r.commits.map((c) => `<span class="commit"><span class="sha">${esc(c.sha)}</span> ${esc(clip(c.subject, 56))} <span class="faint">${esc(ago(c.at))}</span></span>`).join("<br>")}</b>` : `<span>commits</span><b class="faint">none yet</b>`}
      ${r.prompt ? `<span>handoff</span><b class="faint">${esc(r.prompt)}</b>` : ""}
    </div>
    ${relations}
    <div class="actions"><span class="muted">copy:</span>${r.prompt ? `<button type="button" data-copy-handoff="${esc(r.id)}" data-label="handoff" title="copy the handoff document">[handoff]</button>` : ""}<button type="button" data-copy="${esc(r.id)}" data-label="id">[id]</button><button type="button" data-copy="agent-do manna show ${esc(r.id)}" data-label="show cmd">[show cmd]</button></div>`);
  ensureSummary(r.id, summaryKey);
}
const summaries = new Map(); // id -> {summary, error, pending}
const SUMMARY_OPEN_KEY = "manna-serve-summary-open";
const itemSummaryKey = (r) => JSON.stringify([r.title || "", r.description || "", r.type || "item"]);
function summaryOpen() { try { return localStorage.getItem(SUMMARY_OPEN_KEY) !== "0"; } catch { return true; } }
document.addEventListener("toggle", (e) => { if (e.target?.id === "summary-block") { try { localStorage.setItem(SUMMARY_OPEN_KEY, e.target.open ? "1" : "0"); } catch {} } }, true);
function summaryBody(id) {
  const st = summaries.get(id);
  if (!st || st.pending) return '<p class="pending">writing…</p>';
  if (st.summary) return st.summary.split(/\n\n/).map((p) => `<p>${esc(p)}</p>`).join("");
  return `<p class="pending">${esc(st.error || "no summary")}</p>`;
}
async function ensureSummary(id, key) {
  const st = summaries.get(id);
  if (st && (st.pending || st.summary)) return;
  summaries.set(id, { pending: true, key });
  try {
    const r = await fetch(`${api("api/summary")}?id=${encodeURIComponent(id)}`, { cache: "no-store" });
    const d = await r.json();
    if (summaries.get(id)?.key === key) {
      summaries.set(id, { summary: d.summary || null, error: d.error || null, key });
    }
  } catch (e) {
    if (summaries.get(id)?.key === key) {
      summaries.set(id, { summary: null, error: "summary request failed", key });
    }
  }
  if (app.selected?.kind === "item" && app.selected.id === id) { const el = $("#summary-block .summary-body"); if (el) el.innerHTML = summaryBody(id); }
}
// Copy is delegated and capture-phase: buttons re-render with every state
// push, so per-button listeners go stale the moment they are bound, and the
// row's own click handler must never steal a copy click. The async clipboard
// API can reject even on localhost; the textarea fallback runs inside the
// same user gesture, where execCommand still works everywhere.
async function copyText(text, b, note) {
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
  }
  if (ok) {
    if (b) { b.textContent = "[copied]"; b.classList.add("copied"); window.setTimeout(() => { b.textContent = `[${b.dataset.label}]`; b.classList.remove("copied"); }, 1600); }
    toast(`copied ${note || text}`);
  } else {
    toast(`copy failed; select it: ${text}`);
  }
  return ok;
}
// Copy fires on pointerdown, not click: a click needs its button alive from
// press to release, and a state push in between destroys the node — the
// press itself is the earliest moment the node is provably alive, and it is
// a user gesture, which the clipboard APIs require.
document.addEventListener("pointerdown", (e) => {
  const b = e.target.closest?.("[data-copy],[data-copy-handoff]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  if (b.dataset.copy !== undefined) { copyText(b.dataset.copy, b); return; }
  const id = b.dataset.copyHandoff;
  fetch(`${api("api/handoff")}?id=${encodeURIComponent(id)}`, { cache: "no-store" })
    .then((r) => r.json())
    .then((d) => { if (d.content) copyText(d.content, b, `handoff ${d.path} (${d.content.length} chars)`); else toast(d.error || "no handoff content"); })
    .catch(() => toast("handoff request failed"));
}, true);
// The click that follows a copy press must not reach the row handler.
document.addEventListener("click", (e) => {
  if (e.target.closest?.("[data-copy],[data-copy-handoff]")) { e.preventDefault(); e.stopPropagation(); }
}, true);

// ------------------------------------------------------------ columns
// Every column except the flexible digest/text cell is fitted to its widest
// cell. The font is monospace, so width = characters × advance, measured
// once from the live font; the user may drag any grip (stored per browser)
// and double-click it to return to the fit.
const COLS_KEY = "manna-serve-cols-v2"; // v2: widths stored under the old key were fitted by a buggy measure
const COLS = {
  board:   [{ h: "" }, { h: "id", v: "--w-id", sel: ".id" }, { h: "digest", flex: true }, { h: "track", v: "--w-track", sel: ".track", max: 30 }, { h: "state", v: "--w-state", sel: ".pill", max: 24 }, { h: "#", v: "--w-prio", sel: ".prio" }],
  inbox:   [{ h: "" }, { h: "kind", v: "--w-kind", sel: ".kind" }, { h: "ask", flex: true }, { h: "verb", v: "--w-verb", sel: ".verb, .verb-group" }],
  peer:    [{ h: "" }, { h: "session", v: "--w-peer", sel: ".id" }, { h: "focus", flex: true }, { h: "holding", v: "--w-hold", sel: ".track" }, { h: "state", v: "--w-pstate", sel: ".pill" }, { h: "age", v: "--w-age", sel: ".age" }],
  claim:   [{ h: "" }, { h: "path", flex: true }, { h: "owner", v: "--w-owner", sel: ".id" }, { h: "state", v: "--w-cstate", sel: ".pill" }, { h: "age", v: "--w-age", sel: ".age" }],
  drop:    [{ h: "" }, { h: "from → for", v: "--w-from", sel: ".id" }, { h: "drop", flex: true }, { h: "age", v: "--w-age", sel: ".age" }],
  finding: [{ h: "" }, { h: "kind", v: "--w-fkind", sel: ".kind" }, { h: "item", v: "--w-fid", sel: ".id" }, { h: "detail", flex: true }],
};
function loadCols() { try { return JSON.parse(localStorage.getItem(COLS_KEY) || "{}") || {}; } catch { return {}; } }
function saveCols(v) { try { localStorage.setItem(COLS_KEY, JSON.stringify(v)); } catch {} }
let charAdvance = 0;
function measureAdvance() {
  const probe = document.createElement("span");
  probe.textContent = "0".repeat(100); probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap;font:inherit;letter-spacing:.06em";
  document.body.appendChild(probe); charAdvance = probe.getBoundingClientRect().width / 100; probe.remove();
}
function colsHeader(kind, relabel) {
  const cols = COLS[kind]; const flex = cols.findIndex((c) => c.flex);
  return `<div class="cols ${kind}">${cols.map((c, i) => {
    const h = relabel?.[c.h] ?? c.h;
    if (i <= flex) {
      // Left of the flex column: a right-edge grip resizes this column and
      // the flex absorbs the difference, so this boundary moves as dragged.
      if (!c.v) return `<span><span class="hl">${esc(h)}</span></span>`;
      return `<span><span class="hl">${esc(h)}</span><span class="grip grip-right" data-grip="${c.v}" data-dir="1" data-kind="${kind}" title="drag · double-click to refit"></span></span>`;
    }
    const prev = cols[i - 1];
    // Right of the flex column the widths sum to a constant (flex takes the
    // rest), so a boundary between two FIXED columns cannot move by resizing
    // one of them: the drag must transfer width across the boundary (grow the
    // left column, shrink the right by the same amount). Only the boundary
    // adjacent to the flex column resizes a single column.
    const grip = prev.flex
      ? `<span class="grip grip-left" data-grip="${c.v}" data-dir="-1" data-kind="${kind}" title="drag · double-click to refit"></span>`
      : `<span class="grip grip-left" data-grip="${prev.v}" data-dir="1" data-take="${c.v}" data-kind="${kind}" title="drag · double-click to refit"></span>`;
    return `<span><span class="hl">${esc(h)}</span>${grip}</span>`;
  }).join("")}</div>`;
}
// The digest/text cell is the row's actual content; a layout that wraps it
// one word per line is a defect state, not a preference. Enough characters
// for a clause is the floor, and it is checked against rendered pixels —
// stored widths captured under an old fit, a narrower window, or a wild
// drag are discarded the moment they starve the text column.
const MIN_FLEX_CHARS = 24;
function flexStarved(container, kind) {
  const cols = COLS[kind]; const flexIdx = cols.findIndex((c) => c.flex);
  const flexEl = container.querySelectorAll(`.cols.${kind} > span`)[flexIdx];
  return !!flexEl && flexEl.getBoundingClientRect().width < MIN_FLEX_CHARS * charAdvance;
}
function shrinkToFit(container, kind) {
  const cols = COLS[kind]; const flexIdx = cols.findIndex((c) => c.flex);
  const headers = container.querySelectorAll(`.cols.${kind} > span`);
  const flexEl = headers[flexIdx];
  if (!flexEl) return;
  const deficit = MIN_FLEX_CHARS * charAdvance - flexEl.getBoundingClientRect().width;
  if (deficit <= 0) return;
  const style = getComputedStyle(container);
  const entries = [];
  cols.forEach((c, idx) => {
    if (!c.v) return;
    const cur = parseFloat(style.getPropertyValue(c.v));
    if (!cur) return;
    const label = headers[idx]?.querySelector(".hl");
    const floor = (label ? Math.ceil(label.scrollWidth) : 0) + 10;
    if (cur > floor) entries.push({ v: c.v, cur, room: cur - floor });
  });
  const room = entries.reduce((a, x) => a + x.room, 0);
  if (!room) return;
  entries.forEach((x) => container.style.setProperty(x.v, `${Math.round(x.cur - Math.min(1, deficit / room) * x.room)}px`));
}
function fitColumns(container, kind) {
  const cols = COLS[kind]; if (!cols || !container) return;
  if (!charAdvance) measureAdvance();
  applyFit(container, kind, true);
  if (!flexStarved(container, kind)) return;
  const all = loadCols();
  if (all[kind]) { delete all[kind]; saveCols(all); }
  applyFit(container, kind, false);
  if (!flexStarved(container, kind)) return;
  shrinkToFit(container, kind);
}
function applyFit(container, kind, useStored) {
  const cols = COLS[kind];
  const stored = (useStored && loadCols()[kind]) || {};
  const rowSel = kind === "board" ? ".row:not(.inbox):not(.peer):not(.claim):not(.drop):not(.finding)" : `.row.${kind}`;
  const headers = container.querySelectorAll(`.cols.${kind} > span`);
  // Measure content, never the current layout: a span stretched inside an
  // oversized grid column reports the column's width as its own scrollWidth,
  // and the bad width feeds itself back through the fit. Auto first, so
  // every cell shrinks to what it actually holds before it is read.
  cols.forEach((c) => { if (c.v && !stored[c.v]) container.style.setProperty(c.v, "auto"); });
  cols.forEach((c, idx) => {
    if (!c.v) return;
    if (stored[c.v]) { container.style.setProperty(c.v, `${stored[c.v]}px`); return; }
    // Measure real pixels: char-count × advance drifts a few px per cell and
    // the drift becomes a horizontal scrollbar. The header is the floor, so
    // an empty column (nobody holding anything) never collapses under its
    // own label.
    let max = 0;
    container.querySelectorAll(`${rowSel} :is(${c.sel})`).forEach((el) => { max = Math.max(max, el.scrollWidth + (el.classList.contains("verb-group") ? 3 * charAdvance : 0)); });
    if (c.max) max = Math.min(max, Math.ceil(c.max * charAdvance)); // clip long values; the full text rides the cell's title
    const label = headers[idx]?.querySelector(".hl");
    if (label) max = Math.max(max, Math.ceil(label.scrollWidth) + 6);
    container.style.setProperty(c.v, max ? `${Math.ceil(max) + 4}px` : "auto");
  });
}
function bindGrips() {
  $$(".grip").forEach((g) => {
    g.addEventListener("mousedown", (e) => {
      e.preventDefault(); g.classList.add("active");
      const kind = g.dataset.kind, v = g.dataset.grip, take = g.dataset.take || null, container = g.closest(".sheet-body");
      const cssW = (name) => parseFloat(getComputedStyle(container).getPropertyValue(name)) || 0;
      const startX = e.clientX;
      const startW = cssW(v) || (take ? g.parentElement.previousElementSibling : g.parentElement).getBoundingClientRect().width;
      const startB = take ? (cssW(take) || g.parentElement.getBoundingClientRect().width) : 0;
      const dir = Number(g.dataset.dir) || 1;
      const move = (ev) => {
        let dx = dir * (ev.clientX - startX);
        if (take) dx = Math.min(dx, startB - 24); // the shrinking side keeps its floor
        const w = Math.max(24, Math.round(startW + dx));
        container.style.setProperty(v, `${w}px`); g._w = w;
        if (take) { const b = Math.round(startB - (w - startW)); container.style.setProperty(take, `${b}px`); g._b = b; }
      };
      const up = () => {
        window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); g.classList.remove("active");
        if (g._w) { const all = loadCols(); all[kind] = { ...(all[kind] || {}), [v]: g._w, ...(take && g._b ? { [take]: g._b } : {}) }; saveCols(all); }
      };
      window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    });
    g.addEventListener("dblclick", () => { const kind = g.dataset.kind, v = g.dataset.grip, take = g.dataset.take || null; const all = loadCols(); if (all[kind]) { delete all[kind][v]; if (take) delete all[kind][take]; saveCols(all); } fitColumns(g.closest(".sheet-body"), kind); });
  });
}
window.addEventListener("manna-view-changed", () => { charAdvance = 0; renderAll(); });

// ------------------------------------------------------------ chrome
function renderChrome(s) {
  document.title = `manna / ${s.name}`;
  $("#crumb-name").textContent = s.name;
  const asks = inboxRows(s).length;
  $("[data-badge=inbox]").textContent = asks ? String(asks) : "";
  const needs = (s.attention?.["needs-user"] || 0) + (s.attention?.failed || 0);
  $("[data-badge=coord]").textContent = needs ? String(needs) : "";
  renderStrip(s);
  const sel = $("#track-filter");
  const current = sel.value;
  const tracks = (s.tracks || []).map((t) => [t.id || "(none)", shortTrack(t.title)]);
  sel.innerHTML = `<option value="">track ▾</option>` + tracks.map(([id, t]) => `<option value="${esc(id)}"${id === current ? " selected" : ""}>${esc(t)}</option>`).join("");
}
// The strip: board facts on board sheets, coordination facts on the coordination sheet,
// and a word only when something is off. Silence is the health signal.
function renderStrip(s) {
  const el = $("#strip-items"); if (!el || !s) return;
  const parts = [];
  if (app.sheet === "coord") {
    if (s.peers == null) {
      parts.push(`<span class="warn">still reading coordination…</span>`);
    } else {
      const here = (s.peers || []).filter((p) => p.attention !== "gone").length;
      parts.push(`${here} here`, `${s.git?.dirty_paths ?? 0} dirty`);
      const age = Number(s.coord_refreshed_ago), cadence = Number(s.coord_refresh_seconds);
      if (Number.isFinite(age) && Number.isFinite(cadence) && age > 2 * cadence) parts.push(`<span class="warn">presence stale ${Math.round(age)}s</span>`);
    }
  } else if (s.building) {
    parts.push(`<span class="warn">still reading: commits · coord · live drift…</span>`);
  } else {
    const d = s.drift || {};
    if (d.source !== "reconcile" && !d.present) parts.push(`<span class="bad">reconcile unavailable</span>`);
    const dg = s.digests || {};
    if (dg.missing) parts.push(`digests ${dg.ready}/${dg.ready + dg.missing}${dg.generating ? " …" : ""}`);
  }
  el.innerHTML = parts.map((x) => `<span>${x}</span>`).join("");
}
function showSheet(name) {
  app.sheet = name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.sheet === name));
  for (const id of ["inbox", "board", "coord", "debug"]) $(`#sheet-${id}`).hidden = id !== name;
  $("#debug-button").textContent = name === "debug" ? "debug ▾" : "debug ▸";
  if (app.state) renderStrip(app.state);
}
function renderAll() {
  const s = app.state; if (!s) return;
  renderChrome(s); renderInbox(s); renderBoard(s); renderCoord(s); renderDebug(s); renderInspector(s);
  bindGrips();
}

// ------------------------------------------------------------ selection + routing
function select(kind, id, opts = {}) {
  app.selected = { kind, id };
  if (kind === "peer" && !opts.keepSheet) showSheet("coord");
  if (kind === "item" && !opts.keepSheet && app.sheet !== "board" && app.sheet !== "debug") showSheet("board");
  history.replaceState(null, "", `#${kind}/${encodeURIComponent(id)}`);
  renderAll();
  const el = document.querySelector(`[data-${kind}="${CSS.escape(id)}"]`);
  if (el && opts.scroll !== false) el.scrollIntoView({ block: "nearest" });
}
function readHash() {
  const h = location.hash.replace(/^#/, "");
  if (!h) return;
  const [kind, id] = h.split("/");
  if (kind === "item" || kind === "peer") { app.selected = { kind, id: decodeURIComponent(id || "") }; if (kind === "peer") app.sheet = "coord"; }
  else if (["inbox", "board", "coord", "debug"].includes(kind)) {
    app.sheet = kind;
    app.landing = id || null;                       // a section to scroll to once the sheet has rendered
    if (kind === "board" && ["dreams", "done", "now", "next", "waiting", "recent"].includes(id)) { app.view = id; app.landing = null; }
  }
}
// After the first render, scroll the section the hash named into view, once.
function landOnSection() {
  if (!app.landing) return;
  const wanted = app.landing; app.landing = null;
  const label = { now: "manna now", next: "manna next", waiting: "manna waiting", dreams: "manna dreams", done: "manna done", needs: "coord needs you", peers: "coord peers", claims: "coord claims", drops: "coord drops" }[wanted];
  const head = label ? $$(".sheet-head .prompt").find((el) => el.textContent.trim() === label) : null;
  if (head) head.closest(".sheet-head").scrollIntoView({ block: "start" });
}
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-item], [data-peer], [data-target-kind], .tab, .chip, .mode, #debug-button");
  if (!t) return;
  if (t.matches(".tab")) { showSheet(t.dataset.sheet); history.replaceState(null, "", `#${t.dataset.sheet}`); return; }
  if (t.matches("#debug-button")) { showSheet(app.sheet === "debug" ? "board" : "debug"); return; }

  if (t.matches(".chip")) { app.view = t.dataset.chip; $$(".chip").forEach((x) => x.classList.toggle("active", x.dataset.chip === app.view)); renderBoard(app.state); $("#sheet").scrollTo(0, 0); return; }
  if (t.matches(".mode")) { app.mode = t.dataset.mode; $$(".mode").forEach((x) => x.classList.toggle("active", x === t)); renderBoard(app.state); return; }
  if (t.dataset.targetKind) { e.preventDefault(); const k = t.dataset.targetKind, id = t.dataset.targetId; if (k === "sheet") { showSheet(id); history.replaceState(null, "", `#${id}`); } else select(k, id); return; }
  if (t.dataset.item) { e.preventDefault(); select("item", t.dataset.item, { keepSheet: app.sheet === "board" || app.sheet === "debug" }); return; }
  if (t.dataset.peer) { e.preventDefault(); select("peer", t.dataset.peer, { keepSheet: true }); return; }
});
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#grep").focus(); $("#grep").select(); return; }
  if (e.key === "Escape") { clearAnswer(); if (document.activeElement === $("#grep")) { $("#grep").value = ""; app.grep = ""; renderAll(); } return; }
  if (e.key === "Enter" && e.target.matches(".row")) { e.target.click(); }
});
$("#track-filter").addEventListener("change", (e) => { app.track = e.target.value; renderBoard(app.state); });
$("#grep").addEventListener("input", (e) => { app.grep = e.target.value.trim(); if (app.answer && !app.answer.pending) { app.answer = null; renderAnswer(); } renderAll(); });

// ------------------------------------------------------------ ask
// The bar greps as you type; Enter asks the model, which answers from the
// board's own rows and cites ids. The answer sits above the sheet; its
// cited ids become links and a filter until dismissed.
app.answer = null;
function clearAnswer() { if (app.answer) { app.answer = null; renderAnswer(); renderAll(); } }
function renderAnswer() {
  const box = $("#answer");
  if (!app.answer) { box.hidden = true; box.innerHTML = ""; return; }
  const a = app.answer;
  box.hidden = false;
  if (a.pending) { box.innerHTML = `<div class="answer-head"><span class="tag">AI answer</span><span class="faint">thinking…</span></div>`; return; }
  const text = a.error ? `<p class="pending">${esc(a.error)}</p>` : esc(a.answer || "").replace(/\bmn-[0-9a-f]{6,}\b/g, (id) => `<a href="#item/${id}" data-item="${id}">${id}</a>`).split(/\n\n/).map((par) => `<p>${par}</p>`).join("");
  box.innerHTML = `<div class="answer-head"><span class="tag">AI answer</span><span class="faint">${esc(a.question)}</span><button type="button" class="text-button" id="answer-close">[dismiss]</button></div>${text}`;
  $("#answer-close")?.addEventListener("click", clearAnswer);
}
async function ask(question) {
  app.answer = { question, pending: true }; renderAnswer();
  try {
    const r = await fetch(`${api("api/ask")}?q=${encodeURIComponent(question)}`, { cache: "no-store" });
    const d = await r.json();
    app.answer = { question, answer: d.answer || null, cited: d.cited || [], error: d.error || null };
  } catch (e) { app.answer = { question, error: "ask failed" }; }
  renderAnswer(); renderAll();
}
$("#grep").addEventListener("keydown", (e) => { if (e.key === "Enter") { const q = e.target.value.trim(); if (q) { e.preventDefault(); ask(q); } } });

// ------------------------------------------------------------ live
function setConn(ok, text) { $("#connection-mark").textContent = ok ? "●" : "○"; $("#connection-mark").classList.toggle("live", ok); $("#connection-label").textContent = text; }
function receive(state) { app.state = state; app.lastReceived = new Date(); setConn(true, "live"); renderAll(); landOnSection(); }
async function fetchState() {
  // the cheap board first (instant), then the full one (commits, coord, live drift)
  if (!app.state) {
    try { const r = await fetch(api("api/state") + "?fast=1", { cache: "no-store" }); if (r.ok) receive(await r.json()); } catch (e) {}
  }
  try { const r = await fetch(api("api/state"), { cache: "no-store" }); if (!r.ok) throw new Error(`state request failed: ${r.status}`); receive(await r.json()); }
  catch (e) { setConn(false, "disconnected"); toast(e.message); }
}
function connect() {
  const src = new EventSource(api("api/events"));
  src.addEventListener("state", (ev) => { try { receive(JSON.parse(ev.data)); } catch { setConn(false, "bad state"); } });
  src.onopen = () => setConn(true, "live");
  src.onerror = () => setConn(false, "reconnecting");
}
readHash();
showSheet(app.sheet);
$$(".chip").forEach((x) => x.classList.toggle("active", x.dataset.chip === app.view));
fetchState();
connect();
window.setInterval(() => { $("#last-sync").textContent = rel(app.lastReceived); }, 1000);
