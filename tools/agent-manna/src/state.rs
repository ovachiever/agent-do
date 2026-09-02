//! Canonical, read-only Manna board state.
//!
//! The board page and native clients consume this model. Durable Manna rows
//! remain the authority; this module only joins them with handoff priority,
//! blocker topology, Git receipts, federation declarations, drift, and coord
//! presence. Private ownership proofs are removed before any derived row is
//! built, so no repeated section can accidentally serialize them later.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use chrono::{DateTime, SecondsFormat, Utc};
use serde_json::{json, Map, Value};

use crate::federation;
use crate::issue::{Issue, IssueStatus, IssueType};
use crate::reconcile::manna_trailer_ids;
use crate::store::MannaStore;

pub const DEFAULT_DECISION_MARKERS: &[&str] = &["[DECISION]", "[HUMAN]", "[OWNER]"];
const ATTENTION_ORDER: &[&str] = &[
    "needs-user",
    "failed",
    "working",
    "present",
    "idle",
    "finished",
    "ended",
    "gone",
];
const LIVE_OWNERS: &[&str] = &["active", "idle"];

#[derive(Debug, Clone)]
pub struct StateOptions {
    pub decision_markers: Vec<String>,
    pub agent_do: Option<PathBuf>,
    pub live_drift: bool,
    /// A caller-supplied coord snapshot (JSON file holding `{"peers": [...],
    /// "coord": {...}}`). When present, presence is read from this file instead
    /// of being fetched, so the caller's cache signature and this payload are
    /// built from the same observation. Attention is still ranked here: the
    /// core stays the one authority for what a peer's state means.
    pub coord_file: Option<PathBuf>,
}

impl Default for StateOptions {
    fn default() -> Self {
        let agent_do = match std::env::var("MANNA_STATE_AGENT_DO") {
            Ok(value) if value.trim().is_empty() || value == "none" => None,
            Ok(value) => Some(PathBuf::from(value)),
            Err(_) => Some(PathBuf::from("agent-do")),
        };
        let coord_file = match std::env::var("MANNA_STATE_COORD_FILE") {
            Ok(value) if !value.trim().is_empty() => Some(PathBuf::from(value)),
            _ => None,
        };
        StateOptions {
            decision_markers: DEFAULT_DECISION_MARKERS
                .iter()
                .map(|marker| marker.to_string())
                .collect(),
            agent_do,
            live_drift: std::env::var("MANNA_STATE_LIVE_DRIFT").as_deref() != Ok("0"),
            coord_file,
        }
    }
}

#[derive(Debug)]
struct Captured {
    stdout: String,
    status: i32,
}

fn capture(mut command: Command, timeout: Duration) -> Result<Captured, String> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|error| format!("command unavailable: {error}"))?;
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| "command stdout unavailable".to_string())?;
    let mut stderr = child
        .stderr
        .take()
        .ok_or_else(|| "command stderr unavailable".to_string())?;
    let (tx, rx) = mpsc::channel();
    let tx_out = tx.clone();
    thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = stdout.read_to_end(&mut bytes);
        let _ = tx_out.send((true, bytes));
    });
    thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = stderr.read_to_end(&mut bytes);
        let _ = tx.send((false, bytes));
    });

    let deadline = Instant::now() + timeout;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(25)),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("command timed out after {}s", timeout.as_secs()));
            }
            Err(error) => return Err(format!("command wait failed: {error}")),
        }
    };

    let mut stdout_bytes = Vec::new();
    let mut stderr_bytes = Vec::new();
    for _ in 0..2 {
        let (is_stdout, bytes) = rx
            .recv_timeout(Duration::from_secs(1))
            .map_err(|_| "command output drain timed out".to_string())?;
        if is_stdout {
            stdout_bytes = bytes;
        } else {
            stderr_bytes = bytes;
        }
    }
    if !status.success() && stdout_bytes.is_empty() {
        let stderr = String::from_utf8_lossy(&stderr_bytes);
        return Err(stderr.trim().chars().take(240).collect());
    }
    Ok(Captured {
        stdout: String::from_utf8_lossy(&stdout_bytes).into_owned(),
        status: status.code().unwrap_or(-1),
    })
}

fn run(root: &Path, program: &Path, args: &[&str], timeout: Duration) -> Result<Captured, String> {
    let mut command = Command::new(program);
    command.current_dir(root).args(args);
    capture(command, timeout)
}

fn json_command(
    root: &Path,
    program: &Path,
    args: &[&str],
    timeout: Duration,
) -> Result<Value, String> {
    let captured = run(root, program, args, timeout)?;
    serde_json::from_str(&captured.stdout).map_err(|error| {
        format!(
            "command returned invalid JSON (exit {}): {error}",
            captured.status
        )
    })
}

fn executable_file(path: &Path) -> bool {
    let Ok(metadata) = fs::metadata(path) else {
        return false;
    };
    if !metadata.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

fn resolve_executable(program: &Path) -> Option<PathBuf> {
    if program.components().count() > 1 {
        return fs::canonicalize(program)
            .ok()
            .filter(|path| executable_file(path));
    }
    std::env::var_os("PATH")
        .into_iter()
        .flat_map(|paths| std::env::split_paths(&paths).collect::<Vec<_>>())
        .map(|directory| directory.join(program))
        .find(|path| executable_file(path))
        .and_then(|path| fs::canonicalize(path).ok())
}

/// Prefer the router's own agent-coord executable when this is a source-tree
/// installation. The fallback preserves packaged/custom agent-do adapters.
pub fn direct_coord_program(agent_do: &Path) -> Option<PathBuf> {
    let router = resolve_executable(agent_do)?;
    let candidate = router.parent()?.join("tools").join("agent-coord");
    executable_file(&candidate).then_some(candidate)
}

fn coord_json_command(
    root: &Path,
    agent_do: &Path,
    args: &[&str],
    timeout: Duration,
) -> Result<Value, String> {
    if let Some(agent_coord) = direct_coord_program(agent_do) {
        return json_command(root, &agent_coord, args, timeout);
    }
    let mut routed_args = Vec::with_capacity(args.len() + 1);
    routed_args.push("coord");
    routed_args.extend_from_slice(args);
    json_command(root, agent_do, &routed_args, timeout)
}

fn git(root: &Path, args: &[&str], timeout: Duration) -> Result<Captured, String> {
    run(root, Path::new("git"), args, timeout)
}

fn iso_now() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}

fn modified_at(path: &Path) -> Option<String> {
    fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .ok()
        .map(DateTime::<Utc>::from)
        .map(|value| value.to_rfc3339_opts(SecondsFormat::Micros, true))
}

fn yaml_object(path: &Path) -> Map<String, Value> {
    let Ok(text) = fs::read_to_string(path) else {
        return Map::new();
    };
    let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) else {
        return Map::new();
    };
    serde_json::to_value(yaml)
        .ok()
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default()
}

fn string(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(Value::as_str).map(str::to_string)
}

fn string_or_null(value: Option<String>) -> Value {
    value.map(Value::String).unwrap_or(Value::Null)
}

fn attention_position(value: &str) -> usize {
    ATTENTION_ORDER
        .iter()
        .position(|candidate| *candidate == value)
        .unwrap_or(ATTENTION_ORDER.len())
}

fn slim_pulse(value: Option<&Value>) -> Value {
    let Some(pulse) = value.and_then(Value::as_object) else {
        return Value::Null;
    };
    let mut out = Map::new();
    for key in ["status", "activity", "latest_prompt", "updated_at", "turns"] {
        out.insert(
            key.to_string(),
            pulse.get(key).cloned().unwrap_or(Value::Null),
        );
    }
    if let Some(todo) = pulse.get("todo").and_then(Value::as_object) {
        out.insert(
            "todo".to_string(),
            json!({
                "done": todo.get("done").cloned().unwrap_or(Value::Null),
                "total": todo.get("total").cloned().unwrap_or(Value::Null),
                "current": todo.get("current").cloned().unwrap_or(Value::Null),
            }),
        );
    }
    Value::Object(out)
}

fn attention_rank(peer: &Value) -> &'static str {
    let liveness = peer.get("status").and_then(Value::as_str).unwrap_or("");
    let pulse_status = peer
        .get("pulse")
        .and_then(Value::as_object)
        .and_then(|pulse| pulse.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if matches!(liveness, "dead" | "stopped" | "stale") {
        return "gone";
    }
    match pulse_status {
        "needs-user" => "needs-user",
        "failed" => "failed",
        "working" => "working",
        "idle" => "idle",
        "finished" => "finished",
        "ended" => "ended",
        _ if liveness == "idle" => "idle",
        _ => "present",
    }
}

fn collect_peers(root: &Path, agent_do: Option<&Path>) -> Vec<Value> {
    let Some(agent_do) = agent_do else {
        return Vec::new();
    };
    let Ok(payload) = coord_json_command(
        root,
        agent_do,
        &["peers", "--json"],
        Duration::from_secs(10),
    ) else {
        return Vec::new();
    };
    let Some(raw) = payload.get("peers").and_then(Value::as_array) else {
        return Vec::new();
    };
    raw.iter()
        .filter_map(Value::as_object)
        .map(|peer| {
            let focus = peer.get("focus").and_then(Value::as_object);
            let paths = focus
                .and_then(|value| value.get("paths"))
                .filter(|value| value.as_array().is_some_and(|items| !items.is_empty()))
                .cloned()
                .or_else(|| peer.get("territory").cloned())
                .unwrap_or_else(|| json!([]));
            let mut slim = json!({
                "agent_id": peer.get("agent_id").cloned().unwrap_or(Value::Null),
                "alias": peer.get("alias").cloned().unwrap_or(Value::Null),
                "status": peer.get("status").cloned().unwrap_or(Value::Null),
                "age": peer.get("age").cloned().unwrap_or(Value::Null),
                "age_seconds": peer.get("age_seconds").cloned().unwrap_or(Value::Null),
                "runtime": peer.get("runtime").cloned().unwrap_or(Value::Null),
                "role": peer.get("role").cloned().unwrap_or(Value::Null),
                "mode": peer.get("mode").cloned().unwrap_or(Value::Null),
                "phase": peer.get("phase").cloned().unwrap_or(Value::Null),
                "goal": focus.and_then(|value| value.get("goal")).cloned().unwrap_or(Value::Null),
                "paths": paths,
                "pulse": slim_pulse(peer.get("pulse")),
            });
            let rank = attention_rank(&slim);
            slim.as_object_mut()
                .unwrap()
                .insert("attention".to_string(), Value::String(rank.to_string()));
            slim
        })
        .collect()
}

fn coord_rows(root: &Path, agent_do: &Path, args: &[&str], key: &str) -> Vec<Value> {
    coord_json_command(root, agent_do, args, Duration::from_secs(10))
        .ok()
        .and_then(|payload| payload.get(key).and_then(Value::as_array).cloned())
        .unwrap_or_default()
        .into_iter()
        .filter(Value::is_object)
        .collect()
}

fn overlaps(left: &str, right: &str) -> bool {
    let left = left.trim_end_matches('/');
    let right = right.trim_end_matches('/');
    left == right
        || left == "."
        || right == "."
        || left
            .strip_prefix(right)
            .is_some_and(|suffix| suffix.starts_with('/'))
        || right
            .strip_prefix(left)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn empty_coord() -> Value {
    json!({"claims": [], "contention": [], "drops": [], "needs": []})
}

fn collect_coord(root: &Path, agent_do: Option<&Path>, peers: &[Value]) -> Value {
    let Some(agent_do) = agent_do.filter(|_| !peers.is_empty()) else {
        return empty_coord();
    };
    let (claim_rows, drop_rows, need_rows) = thread::scope(|scope| {
        let claims = scope.spawn(|| coord_rows(root, agent_do, &["claims", "--json"], "claims"));
        let drops = scope.spawn(|| coord_rows(root, agent_do, &["drops", "--json"], "drops"));
        let needs = scope.spawn(|| {
            coord_rows(
                root,
                agent_do,
                &["need", "list", "--all", "--json"],
                "needs",
            )
        });
        (
            claims.join().unwrap_or_default(),
            drops.join().unwrap_or_default(),
            needs.join().unwrap_or_default(),
        )
    });
    let mut claims: Vec<Value> = claim_rows
    .into_iter()
    .map(|claim| {
        let owner_status = string(&claim, "owner_status");
        json!({
            "path": claim.get("path").cloned().unwrap_or(Value::Null),
            "owner": claim.get("owner").cloned().unwrap_or(Value::Null),
            "owner_alias": claim.get("owner_alias").cloned().unwrap_or(Value::Null),
            "owner_status": string_or_null(owner_status.clone()),
            "reason": claim.get("reason").cloned().unwrap_or(Value::Null),
            "strength": claim.get("strength").cloned().unwrap_or(Value::Null),
            "updated_at": claim.get("updated_at").or_else(|| claim.get("created_at")).cloned().unwrap_or(Value::Null),
            "stale": !owner_status.as_deref().is_some_and(|status| LIVE_OWNERS.contains(&status)),
            "contended": false,
        })
    })
    .collect();

    let live: Vec<(String, String)> = claims
        .iter()
        .filter(|claim| claim.get("stale") == Some(&Value::Bool(false)))
        .filter_map(|claim| Some((string(claim, "owner")?, string(claim, "path")?)))
        .collect();
    let mut contention = Vec::new();
    let mut seen = HashSet::new();
    for (index, left) in live.iter().enumerate() {
        for right in live.iter().skip(index + 1) {
            if left.0 == right.0 || !overlaps(&left.1, &right.1) {
                continue;
            }
            let mut keys = [
                format!("{}:{}", left.0, left.1),
                format!("{}:{}", right.0, right.1),
            ];
            keys.sort();
            if !seen.insert(keys.join("|")) {
                continue;
            }
            let mut paths = vec![left.1.clone(), right.1.clone()];
            paths.sort();
            paths.dedup();
            let mut owners = vec![left.0.clone(), right.0.clone()];
            owners.sort();
            owners.dedup();
            contention.push(json!({"paths": paths, "owners": owners}));
        }
    }
    for claim in &mut claims {
        let owner = string(claim, "owner").unwrap_or_default();
        let path = string(claim, "path").unwrap_or_default();
        let contended = contention.iter().any(|row| {
            row.get("owners")
                .and_then(Value::as_array)
                .is_some_and(|values| {
                    values
                        .iter()
                        .any(|value| value == &Value::String(owner.clone()))
                })
                && row
                    .get("paths")
                    .and_then(Value::as_array)
                    .is_some_and(|values| {
                        values
                            .iter()
                            .any(|value| value == &Value::String(path.clone()))
                    })
        });
        claim
            .as_object_mut()
            .unwrap()
            .insert("contended".to_string(), Value::Bool(contended));
    }
    claims.sort_by(|left, right| {
        let left_key = (
            left.get("stale").and_then(Value::as_bool).unwrap_or(true),
            !left
                .get("contended")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            string(left, "path").unwrap_or_default(),
        );
        let right_key = (
            right.get("stale").and_then(Value::as_bool).unwrap_or(true),
            !right
                .get("contended")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            string(right, "path").unwrap_or_default(),
        );
        left_key.cmp(&right_key)
    });

    let mut drops: Vec<Value> = drop_rows
        .into_iter()
    .map(|drop| {
        json!({
            "for": drop.get("for").cloned().unwrap_or(Value::Null),
            "path": drop.get("path").or_else(|| drop.get("paths")).cloned().unwrap_or(Value::Null),
            "note": drop.get("note").cloned().unwrap_or(Value::Null),
            "owner": drop.get("owner_label").or_else(|| drop.get("owner")).cloned().unwrap_or(Value::Null),
            "key": drop.get("key").cloned().unwrap_or(Value::Null),
            "created_at": drop.get("created_at").cloned().unwrap_or(Value::Null),
        })
    })
    .collect();
    drops.sort_by(|left, right| {
        string(right, "created_at")
            .unwrap_or_default()
            .cmp(&string(left, "created_at").unwrap_or_default())
    });
    let needs: Vec<Value> = need_rows
        .into_iter()
    .map(|need| {
        json!({
            "key": need.get("key").cloned().unwrap_or(Value::Null),
            "why": need.get("why").cloned().unwrap_or(Value::Null),
            "owner": need.get("owner").or_else(|| need.get("owner_label")).cloned().unwrap_or(Value::Null),
        })
    })
    .collect();
    json!({"claims": claims, "contention": contention, "drops": drops, "needs": needs})
}

/// Read a caller-supplied coord snapshot. Peer rows are taken as given (they
/// are the same slim shape `collect_peers` builds) except for `attention`,
/// which is always re-ranked here so a caller cannot ship a stale or divergent
/// ranking into the canonical model.
fn coord_overlay(options: &StateOptions) -> Option<(Vec<Value>, Value)> {
    let path = options.coord_file.as_deref()?;
    let text = fs::read_to_string(path).ok()?;
    let payload: Value = serde_json::from_str(&text).ok()?;
    let peers: Vec<Value> = payload
        .get("peers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter(Value::is_object)
        .map(|mut peer| {
            let rank = attention_rank(&peer);
            peer.as_object_mut()
                .unwrap()
                .insert("attention".to_string(), Value::String(rank.to_string()));
            peer
        })
        .collect();
    let coord = payload
        .get("coord")
        .filter(|value| value.is_object())
        .cloned()
        .unwrap_or_else(empty_coord);
    Some((peers, coord))
}

fn identity_hex(value: Option<&str>) -> String {
    let Some(value) = value else {
        return String::new();
    };
    let lower = value.to_ascii_lowercase();
    let tail = lower.rsplit('-').next().unwrap_or(&lower);
    if !tail.is_empty() && tail.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        tail.to_string()
    } else {
        lower
    }
}

fn matching_peer(claimed_by: Option<&str>, peers: &[Value]) -> Option<Value> {
    let wanted = identity_hex(claimed_by);
    if wanted.is_empty() {
        return None;
    }
    peers.iter().find_map(|peer| {
        let have = identity_hex(peer.get("agent_id").and_then(Value::as_str));
        (!have.is_empty() && (wanted.starts_with(&have) || have.starts_with(&wanted)))
            .then(|| peer.clone())
    })
}

fn leading_tags(title: &str) -> Vec<String> {
    let mut rest = title.trim_start();
    let mut tags = Vec::new();
    while let Some(after_open) = rest.strip_prefix('[') {
        let Some(close) = after_open.find(']') else {
            break;
        };
        tags.push(format!("[{}]", &after_open[..close]).to_ascii_uppercase());
        rest = after_open[close + 1..].trim_start();
    }
    tags
}

fn is_decision(title: &str, markers: &[String]) -> bool {
    let tags: HashSet<String> = leading_tags(title).into_iter().collect();
    markers
        .iter()
        .any(|marker| tags.contains(&marker.to_ascii_uppercase()))
}

fn strip_markers(title: &str) -> String {
    let mut rest = title.trim_start();
    let original = rest;
    while let Some(after_open) = rest.strip_prefix('[') {
        let Some(close) = after_open.find(']') else {
            break;
        };
        rest = after_open[close + 1..].trim_start();
    }
    let stripped = rest.trim();
    if stripped.is_empty() {
        original.to_string()
    } else {
        stripped.to_string()
    }
}

fn git_summary(root: &Path) -> Value {
    let branch = git(root, &["branch", "--show-current"], Duration::from_secs(5))
        .ok()
        .map(|result| result.stdout.trim().to_string())
        .filter(|value| !value.is_empty());
    let head = git(
        root,
        &["rev-parse", "--short", "HEAD"],
        Duration::from_secs(5),
    )
    .ok()
    .map(|result| result.stdout.trim().to_string())
    .filter(|value| !value.is_empty());
    let dirty_paths = git(root, &["status", "--porcelain"], Duration::from_secs(10))
        .ok()
        .map(|result| result.stdout.lines().count())
        .unwrap_or_default();
    json!({
        "branch": string_or_null(branch),
        "head": string_or_null(head.clone()),
        "dirty_paths": dirty_paths,
        "is_repo": head.is_some(),
    })
}

fn git_trailers(root: &Path, is_repo: bool) -> HashMap<String, Vec<Value>> {
    if !is_repo {
        return HashMap::new();
    }
    let format = "%h%x1f%cI%x1f%s%x1f%B%x1e";
    let Ok(output) = git(
        root,
        &[
            "log",
            &format!("--format={format}"),
            "--grep=^Manna:",
            "--extended-regexp",
        ],
        Duration::from_secs(20),
    ) else {
        return HashMap::new();
    };
    let mut index: HashMap<String, Vec<Value>> = HashMap::new();
    for record in output.stdout.split('\x1e') {
        let record = record.trim_matches('\n');
        let parts: Vec<&str> = record.splitn(4, '\x1f').collect();
        if parts.len() != 4 {
            continue;
        }
        let (sha, at, subject, body) = (parts[0], parts[1], parts[2], parts[3]);
        for id in manna_trailer_ids(body) {
            index.entry(id).or_default().push(json!({
                "sha": sha,
                "at": at,
                "subject": subject,
            }));
        }
    }
    index
}

fn drift_parts(board_dir: &Path) -> (Value, Value) {
    let path = board_dir.join("drift.yaml");
    let data = yaml_object(&path);
    let findings = data
        .get("findings")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter(Value::is_object)
        .collect::<Vec<_>>();
    let mut kinds = Map::new();
    for finding in &findings {
        let kind = finding
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        let next = kinds.get(kind).and_then(Value::as_u64).unwrap_or_default() + 1;
        kinds.insert(kind.to_string(), Value::from(next));
    }
    let generated_at = data.get("generated_at").cloned().unwrap_or(Value::Null);
    let file = json!({
        "present": path.is_file(),
        "generated_at": generated_at,
        "count": findings.len(),
    });
    let drift = json!({
        "present": path.is_file(),
        "generated_at": data.get("generated_at").cloned().unwrap_or(Value::Null),
        "findings": findings,
        "count": file.get("count").cloned().unwrap_or(Value::from(0)),
        "kinds": kinds,
        "source": "file",
        "file": file,
    });
    (
        drift,
        data.get("generated_at").cloned().unwrap_or(Value::Null),
    )
}

/// A running manna-core can reconcile itself directly. Falling back to the
/// agent-do router keeps library embeddings working, while the normal CLI path
/// avoids launching the full router only to return to the same binary.
fn live_reconcile_command(
    agent_do: &Path,
    current_exe: Option<PathBuf>,
) -> (PathBuf, &'static [&'static str]) {
    if let Some(executable) = current_exe.filter(|path| {
        agent_do == Path::new("agent-do")
            && path.file_stem().and_then(|name| name.to_str()) == Some("manna-core")
    }) {
        return (executable, &["reconcile", "--json"]);
    }
    (agent_do.to_path_buf(), &["manna", "reconcile", "--json"])
}

fn drift_state(root: &Path, board_dir: &Path, options: &StateOptions) -> Value {
    let (file_drift, _) = drift_parts(board_dir);
    let Some(agent_do) = options.agent_do.as_deref().filter(|_| options.live_drift) else {
        return file_drift;
    };
    let (program, args) = live_reconcile_command(agent_do, std::env::current_exe().ok());
    let Ok(payload) = json_command(root, &program, args, Duration::from_secs(60)) else {
        return file_drift;
    };
    let Some(findings) = payload.get("findings").and_then(Value::as_array).cloned() else {
        return file_drift;
    };
    let findings: Vec<Value> = findings.into_iter().filter(Value::is_object).collect();
    let mut kinds = Map::new();
    for finding in &findings {
        let kind = finding
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        let next = kinds.get(kind).and_then(Value::as_u64).unwrap_or_default() + 1;
        kinds.insert(kind.to_string(), Value::from(next));
    }
    json!({
        "present": true,
        "generated_at": iso_now(),
        "findings": findings,
        "count": findings.len(),
        "kinds": kinds,
        "source": "reconcile",
        "file": file_drift.get("file").cloned().unwrap_or(Value::Null),
    })
}

fn federation_state(root: &Path, issues: &[Issue]) -> (Value, HashMap<String, Vec<Value>>) {
    let path_exists = root.join(".manna/federation.yaml").is_file();
    let manifest = federation::load_manifest(root, Some(issues));
    let mut by_source: HashMap<String, Vec<Value>> = HashMap::new();
    match manifest {
        Ok(Some(manifest)) => {
            let reports = federation::relations(root, issues, None, true)
                .ok()
                .and_then(|value| serde_json::to_value(value).ok())
                .and_then(|value| value.get("relations").and_then(Value::as_array).cloned())
                .unwrap_or_else(|| {
                    manifest
                        .relations
                        .iter()
                        .filter_map(|relation| serde_json::to_value(relation).ok())
                        .collect()
                });
            for relation in &reports {
                if let Some(source) = relation.get("from").and_then(Value::as_str) {
                    by_source
                        .entry(source.to_string())
                        .or_default()
                        .push(relation.clone());
                }
            }
            (
                json!({
                    "enabled": true,
                    "board_id": manifest.board_id,
                    "relations": reports,
                }),
                by_source,
            )
        }
        Ok(None) => (
            json!({"enabled": false, "board_id": null, "relations": []}),
            by_source,
        ),
        Err(error) => (
            json!({
                "enabled": path_exists,
                "board_id": null,
                "relations": [],
                "error": error,
            }),
            by_source,
        ),
    }
}

fn order_cmp(left: &Value, right: &Value) -> Ordering {
    let left_pos = left.get("order").and_then(Value::as_u64);
    let right_pos = right.get("order").and_then(Value::as_u64);
    match (left_pos, right_pos) {
        (Some(left), Some(right)) if left != right => left.cmp(&right),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        _ => string(left, "updated_at")
            .unwrap_or_default()
            .cmp(&string(right, "updated_at").unwrap_or_default())
            .then_with(|| {
                string(left, "id")
                    .unwrap_or_default()
                    .cmp(&string(right, "id").unwrap_or_default())
            }),
    }
}

fn now_cmp(left: &Value, right: &Value) -> Ordering {
    let left_rank = left
        .get("claimant")
        .and_then(Value::as_object)
        .and_then(|claimant| claimant.get("attention"))
        .and_then(Value::as_str)
        .unwrap_or("unseen");
    let right_rank = right
        .get("claimant")
        .and_then(Value::as_object)
        .and_then(|claimant| claimant.get("attention"))
        .and_then(Value::as_str)
        .unwrap_or("unseen");
    attention_position(left_rank)
        .cmp(&attention_position(right_rank))
        .then_with(|| order_cmp(left, right))
}

fn public_issue(issue: &Issue) -> Result<Map<String, Value>, String> {
    let mut value = serde_json::to_value(issue).map_err(|error| error.to_string())?;
    let row = value
        .as_object_mut()
        .ok_or_else(|| "issue did not serialize as an object".to_string())?;
    row.remove("claim_token_hash");
    row.remove("legacy_migration");
    Ok(row.clone())
}

struct DeriveInputs<'a> {
    root: &'a Path,
    issues: &'a [Issue],
    order: &'a [String],
    markers: &'a [String],
    peers: Vec<Value>,
    coord: Value,
    git_state: Value,
    trailers: &'a HashMap<String, Vec<Value>>,
    drift: Value,
    federation: Value,
    relations: &'a HashMap<String, Vec<Value>>,
}

fn derive(inputs: DeriveInputs<'_>) -> Result<Value, String> {
    let DeriveInputs {
        root,
        issues,
        order,
        markers,
        mut peers,
        coord,
        git_state,
        trailers,
        drift,
        federation,
        relations,
    } = inputs;
    let board_dir = root.join(".manna");
    let workflow = yaml_object(&board_dir.join("workflow.yaml"));
    let board_meta = yaml_object(&board_dir.join("board.yaml"));
    let handoff_dir = workflow
        .get("handoff_dir")
        .and_then(Value::as_str)
        .unwrap_or(".handoff")
        .to_string();
    let order_index: HashMap<&str, usize> = order
        .iter()
        .enumerate()
        .map(|(index, id)| (id.as_str(), index))
        .collect();
    let by_id: HashMap<&str, &Issue> = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect();
    let track_titles: HashMap<&str, &str> = issues
        .iter()
        .filter(|issue| issue.issue_type == IssueType::Track)
        .map(|issue| (issue.id.as_str(), issue.title.as_str()))
        .collect();

    let mut rows = Vec::new();
    for issue in issues {
        let blockers: Vec<Value> = issue
            .blocked_by
            .iter()
            .filter_map(|blocker| match by_id.get(blocker.as_str()) {
                Some(target) if target.status == IssueStatus::Done => None,
                Some(target) => Some(json!({
                    "id": blocker,
                    "status": target.status.to_string(),
                    "title": target.title,
                })),
                None => Some(json!({"id": blocker, "status": "missing", "title": blocker})),
            })
            .collect();
        let peer = matching_peer(issue.claimed_by.as_deref(), &peers);
        let decision = issue.status != IssueStatus::Done && is_decision(&issue.title, markers);
        let kind = issue.issue_type.to_string();
        let effective = match issue.issue_type {
            IssueType::Track => "track",
            IssueType::Dream if issue.status != IssueStatus::Done => "dream",
            IssueType::Dream => "done",
            IssueType::Item if issue.status == IssueStatus::Done => "done",
            IssueType::Item if issue.status == IssueStatus::InProgress => "active",
            IssueType::Item if !blockers.is_empty() => "waiting",
            IssueType::Item if decision => "decision",
            IssueType::Item => "ready",
        };
        let claimant = issue.claimed_by.as_ref().map(|claimed_by| {
            json!({
                "label": claimed_by,
                "liveness": peer.as_ref().and_then(|value| value.get("status")).cloned().unwrap_or_else(|| Value::String("unseen".to_string())),
                "age": peer.as_ref().and_then(|value| value.get("age")).cloned().unwrap_or(Value::Null),
                "runtime": peer.as_ref().and_then(|value| value.get("runtime")).cloned().unwrap_or(Value::Null),
                "goal": peer.as_ref().and_then(|value| value.get("goal")).cloned().unwrap_or(Value::Null),
                "pulse": peer.as_ref().and_then(|value| value.get("pulse")).cloned().unwrap_or(Value::Null),
                "attention": peer.as_ref().and_then(|value| value.get("attention")).cloned().unwrap_or_else(|| Value::String("unseen".to_string())),
            })
        });
        let mut row = public_issue(issue)?;
        row.insert("kind".to_string(), Value::String(kind));
        row.insert(
            "title_plain".to_string(),
            Value::String(strip_markers(&issue.title)),
        );
        row.insert(
            "track_title".to_string(),
            issue
                .track
                .as_deref()
                .and_then(|id| track_titles.get(id).copied())
                .map(|value| Value::String(value.to_string()))
                .unwrap_or(Value::Null),
        );
        row.insert(
            "order".to_string(),
            order_index
                .get(issue.id.as_str())
                .map(|value| Value::from(*value))
                .unwrap_or(Value::Null),
        );
        row.insert(
            "handoff_exists".to_string(),
            issue
                .prompt
                .as_ref()
                .map(|path| Value::Bool(root.join(path).is_file()))
                .unwrap_or(Value::Null),
        );
        row.insert("blockers".to_string(), Value::Array(blockers));
        row.insert("dependents".to_string(), json!([]));
        row.insert("decision".to_string(), Value::Bool(decision));
        row.insert("claimant".to_string(), claimant.unwrap_or(Value::Null));
        row.insert(
            "commits".to_string(),
            Value::Array(trailers.get(&issue.id).cloned().unwrap_or_default()),
        );
        row.insert(
            "relations".to_string(),
            Value::Array(relations.get(&issue.id).cloned().unwrap_or_default()),
        );
        row.insert(
            "effective".to_string(),
            Value::String(effective.to_string()),
        );
        rows.push(Value::Object(row));
    }

    let row_index: HashMap<String, usize> = rows
        .iter()
        .enumerate()
        .filter_map(|(index, row)| Some((string(row, "id")?, index)))
        .collect();
    let edges: Vec<(String, String)> = issues
        .iter()
        .flat_map(|issue| {
            issue
                .blocked_by
                .iter()
                .map(move |blocker| (blocker.clone(), issue.id.clone()))
        })
        .collect();
    for (blocker, dependent) in edges {
        let Some(index) = row_index.get(&blocker).copied() else {
            continue;
        };
        rows[index]
            .get_mut("dependents")
            .and_then(Value::as_array_mut)
            .unwrap()
            .push(Value::String(dependent));
    }

    for peer in &mut peers {
        let holdings: Vec<Value> = rows
            .iter()
            .filter(|row| row.get("status").and_then(Value::as_str) == Some("in_progress"))
            .filter(|row| {
                let claimed_by = row.get("claimed_by").and_then(Value::as_str);
                matching_peer(claimed_by, std::slice::from_ref(peer)).is_some()
            })
            .map(|row| {
                json!({
                    "id": row.get("id").cloned().unwrap_or(Value::Null),
                    "title": row.get("title").cloned().unwrap_or(Value::Null),
                })
            })
            .collect();
        peer.as_object_mut()
            .unwrap()
            .insert("holding".to_string(), Value::Array(holdings));
    }
    peers.sort_by(|left, right| {
        let left_rank = string(left, "attention").unwrap_or_default();
        let right_rank = string(right, "attention").unwrap_or_default();
        attention_position(&left_rank)
            .cmp(&attention_position(&right_rank))
            .then_with(|| {
                left.get("age_seconds")
                    .and_then(Value::as_i64)
                    .unwrap_or(i64::MAX)
                    .cmp(
                        &right
                            .get("age_seconds")
                            .and_then(Value::as_i64)
                            .unwrap_or(i64::MAX),
                    )
            })
    });

    let mut now: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("effective").and_then(Value::as_str) == Some("active"))
        .cloned()
        .collect();
    now.sort_by(now_cmp);
    let mut next: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("effective").and_then(Value::as_str) == Some("ready"))
        .cloned()
        .collect();
    next.sort_by(order_cmp);
    let mut decisions: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("decision").and_then(Value::as_bool) == Some(true))
        .filter(|row| row.get("effective").and_then(Value::as_str) != Some("done"))
        .cloned()
        .collect();
    decisions.sort_by(order_cmp);
    let waiting: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("effective").and_then(Value::as_str) == Some("waiting"))
        .cloned()
        .collect();
    let mut dreams: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("effective").and_then(Value::as_str) == Some("dream"))
        .cloned()
        .collect();
    dreams.sort_by(|left, right| {
        string(right, "updated_at")
            .unwrap_or_default()
            .cmp(&string(left, "updated_at").unwrap_or_default())
    });

    let waiting_by_id: HashMap<String, Value> = waiting
        .iter()
        .filter_map(|row| Some((string(row, "id")?, row.clone())))
        .collect();
    let mut remaining: HashSet<String> = waiting_by_id.keys().cloned().collect();
    let mut waves = Vec::new();
    while !remaining.is_empty() {
        let mut layer: Vec<Value> = remaining
            .iter()
            .filter_map(|id| waiting_by_id.get(id))
            .filter(|row| {
                row.get("blockers")
                    .and_then(Value::as_array)
                    .is_none_or(|blockers| {
                        blockers.iter().all(|blocker| {
                            blocker
                                .get("id")
                                .and_then(Value::as_str)
                                .is_none_or(|id| !remaining.contains(id))
                        })
                    })
            })
            .cloned()
            .collect();
        if layer.is_empty() {
            break;
        }
        layer.sort_by(order_cmp);
        for row in &layer {
            if let Some(id) = row.get("id").and_then(Value::as_str) {
                remaining.remove(id);
            }
        }
        waves.push(json!({"wave": waves.len() + 1, "items": layer}));
    }
    let mut unlayered: Vec<Value> = remaining
        .iter()
        .filter_map(|id| waiting_by_id.get(id).cloned())
        .collect();
    unlayered.sort_by(order_cmp);

    let mut counts = Map::new();
    let mut status_counts = Map::new();
    for row in &rows {
        for (key, field) in [("effective", &mut counts), ("status", &mut status_counts)] {
            let value = row.get(key).and_then(Value::as_str).unwrap_or("open");
            let next = field.get(value).and_then(Value::as_u64).unwrap_or_default() + 1;
            field.insert(value.to_string(), Value::from(next));
        }
    }

    let mut tracks = Vec::new();
    for track in issues
        .iter()
        .filter(|issue| issue.issue_type == IssueType::Track)
    {
        let mut members: Vec<Value> = rows
            .iter()
            .filter(|row| row.get("track").and_then(Value::as_str) == Some(track.id.as_str()))
            .filter(|row| row.get("kind").and_then(Value::as_str) != Some("track"))
            .cloned()
            .collect();
        members.sort_by(order_cmp);
        tracks.push(json!({
            "id": track.id,
            "title": track.title,
            "status": track.status.to_string(),
            "items": members,
        }));
    }
    let mut orphans: Vec<Value> = rows
        .iter()
        .filter(|row| row.get("kind").and_then(Value::as_str) != Some("track"))
        .filter(|row| row.get("track").is_none_or(Value::is_null))
        .cloned()
        .collect();
    orphans.sort_by(order_cmp);
    if !orphans.is_empty() {
        tracks.push(json!({"id": null, "title": "(no track)", "status": null, "items": orphans}));
    }

    let mut all = rows;
    all.sort_by(order_cmp);
    let mut attention = Map::new();
    for rank in ATTENTION_ORDER {
        attention.insert(
            rank.to_string(),
            Value::from(
                peers
                    .iter()
                    .filter(|peer| peer.get("attention").and_then(Value::as_str) == Some(*rank))
                    .count(),
            ),
        );
    }
    Ok(json!({
        "generated_at": iso_now(),
        "root": root.to_string_lossy(),
        "name": root.file_name().and_then(|value| value.to_str()).unwrap_or(""),
        "board": {
            "path": ".manna/issues.jsonl",
            "workflow": board_meta.get("workflow").cloned().unwrap_or(Value::Null),
            "board_id": federation.get("board_id").cloned().unwrap_or(Value::Null),
            "decision_markers": markers,
            "handoff_dir": handoff_dir,
            "issues_modified_at": modified_at(&board_dir.join("issues.jsonl")),
            "order_count": order.len(),
        },
        "git": git_state,
        "peers": peers,
        "attention": attention,
        "coord": coord,
        "counts": counts,
        "status_counts": status_counts,
        "total": issues.len(),
        "now": now,
        "next": next,
        "decisions": decisions,
        "waves": waves,
        "unlayered": unlayered,
        "dreams": dreams,
        "tracks": tracks,
        "drift": drift,
        "federation": federation,
        "all": all,
    }))
}

pub fn derive_board_state(root: &Path, options: &StateOptions) -> Result<Value, String> {
    let root = fs::canonicalize(root)
        .map_err(|error| format!("cannot resolve board root {}: {error}", root.display()))?;
    let store = MannaStore::new(&root);
    if !store.is_initialized() {
        return Err("Storage not initialized. Run 'manna-core init' first.".to_string());
    }
    // A whole-board contract cannot silently look complete after dropping a
    // malformed row. The narrow list/show reads retain their historical
    // tolerant behavior; state fails closed because every section and count
    // claims coverage of the complete board.
    let issues = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let board_dir = root.join(".manna");
    let order = yaml_object(&board_dir.join("handoff-order.yaml"))
        .get("items")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let git_state = git_summary(&root);
    let is_repo = git_state
        .get("is_repo")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let (trailers, peers, coord, drift, federation, relations) = thread::scope(|scope| {
        let trailer_job = scope.spawn(|| git_trailers(&root, is_repo));
        let presence_job = scope.spawn(|| {
            if let Some(overlay) = coord_overlay(options) {
                return overlay;
            }
            let peers = collect_peers(&root, options.agent_do.as_deref());
            let coord = collect_coord(&root, options.agent_do.as_deref(), &peers);
            (peers, coord)
        });
        let drift_job = scope.spawn(|| drift_state(&root, &board_dir, options));
        let federation_job = scope.spawn(|| federation_state(&root, &issues));
        let trailers = trailer_job.join().unwrap_or_default();
        let (peers, coord) = presence_job
            .join()
            .unwrap_or_else(|_| (Vec::new(), empty_coord()));
        let drift = drift_job
            .join()
            .unwrap_or_else(|_| drift_parts(&board_dir).0);
        let (federation, relations) = federation_job.join().unwrap_or_else(|_| {
            (
                json!({"enabled": false, "board_id": null, "relations": [], "error": "state federation worker failed"}),
                HashMap::new(),
            )
        });
        (trailers, peers, coord, drift, federation, relations)
    });
    derive(DeriveInputs {
        root: &root,
        issues: &issues,
        order: &order,
        markers: &options.decision_markers,
        peers,
        coord,
        git_state,
        trailers: &trailers,
        drift,
        federation,
        relations: &relations,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    use tempfile::TempDir;

    #[test]
    fn live_reconcile_uses_the_running_core_without_router_round_trip() {
        let agent_do = Path::new("agent-do");
        let (program, args) = live_reconcile_command(
            agent_do,
            Some(PathBuf::from(
                "/repo/tools/agent-manna/target/release/manna-core",
            )),
        );
        assert_eq!(
            program,
            PathBuf::from("/repo/tools/agent-manna/target/release/manna-core")
        );
        assert_eq!(args, ["reconcile", "--json"]);

        let custom_agent_do = Path::new("/opt/custom-agent-do");
        let (program, args) = live_reconcile_command(
            custom_agent_do,
            Some(PathBuf::from(
                "/repo/tools/agent-manna/target/release/manna-core",
            )),
        );
        assert_eq!(program, custom_agent_do);
        assert_eq!(args, ["manna", "reconcile", "--json"]);
    }

    #[test]
    #[cfg(unix)]
    fn source_tree_state_invokes_agent_coord_without_router_round_trip() {
        use std::os::unix::fs::PermissionsExt;

        let temp = TempDir::new().unwrap();
        let router = temp.path().join("agent-do");
        let coord = temp.path().join("tools/agent-coord");
        fs::create_dir(coord.parent().unwrap()).unwrap();
        fs::write(&router, "#!/bin/sh\n").unwrap();
        fs::write(&coord, "#!/bin/sh\n").unwrap();
        for path in [&router, &coord] {
            let mut permissions = fs::metadata(path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(path, permissions).unwrap();
        }

        assert_eq!(
            direct_coord_program(&router),
            Some(coord.canonicalize().unwrap())
        );
    }

    fn issue(id: &str, title: &str, status: IssueStatus, issue_type: IssueType) -> Issue {
        let mut issue = Issue::new(id.to_string(), title.to_string()).unwrap();
        issue.status = status;
        issue.issue_type = issue_type;
        issue.created_at = Utc.with_ymd_and_hms(2026, 8, 1, 0, 0, 0).unwrap();
        issue.updated_at = issue.created_at;
        issue
    }

    fn fixture() -> (TempDir, Value) {
        let temp = TempDir::new().unwrap();
        fs::create_dir(temp.path().join(".manna")).unwrap();
        fs::write(temp.path().join(".manna/sessions.jsonl"), "").unwrap();
        fs::write(
            temp.path().join(".manna/handoff-order.yaml"),
            "version: 1\nitems:\n- mn-ready1\n- mn-waits1\n",
        )
        .unwrap();
        fs::write(
            temp.path().join(".manna/board.yaml"),
            "version: 1\nworkflow: strict\n",
        )
        .unwrap();
        fs::write(
            temp.path().join(".manna/workflow.yaml"),
            "version: 2\nhandoff_dir: .handoff\n",
        )
        .unwrap();
        let mut track = issue(
            "mn-track1",
            "TRACK: One",
            IssueStatus::Open,
            IssueType::Track,
        );
        let mut ready = issue("mn-ready1", "Ready", IssueStatus::Open, IssueType::Item);
        ready.track = Some(track.id.clone());
        ready.description = Some(
            "Document claim_token_hash and legacy_migration redaction without exposing fields."
                .to_string(),
        );
        ready.claim_token_hash = Some(format!("sha256:{}", "a".repeat(64)));
        let mut waiting = issue(
            "mn-waits1",
            "Waiting",
            IssueStatus::Blocked,
            IssueType::Item,
        );
        waiting.blocked_by = vec![ready.id.clone()];
        let decision = issue(
            "mn-rule11",
            "[HUMAN] Rule",
            IssueStatus::Open,
            IssueType::Item,
        );
        track.legacy_migration = None;
        let issues = [track, ready, waiting, decision];
        fs::write(
            temp.path().join(".manna/issues.jsonl"),
            issues
                .iter()
                .map(|row| serde_json::to_string(row).unwrap() + "\n")
                .collect::<String>(),
        )
        .unwrap();
        let state = derive_board_state(
            temp.path(),
            &StateOptions {
                decision_markers: DEFAULT_DECISION_MARKERS
                    .iter()
                    .map(|value| value.to_string())
                    .collect(),
                agent_do: None,
                live_drift: false,
                coord_file: None,
            },
        )
        .unwrap();
        (temp, state)
    }

    #[test]
    fn state_redacts_private_row_fields_everywhere() {
        let (_temp, state) = fixture();
        fn contains_key(value: &Value, key: &str) -> bool {
            match value {
                Value::Object(object) => {
                    object.contains_key(key)
                        || object.values().any(|child| contains_key(child, key))
                }
                Value::Array(items) => items.iter().any(|child| contains_key(child, key)),
                _ => false,
            }
        }
        assert!(!contains_key(&state, "claim_token_hash"));
        assert!(!contains_key(&state, "legacy_migration"));
    }

    #[test]
    fn state_derives_graph_and_decision_buckets() {
        let (_temp, state) = fixture();
        assert_eq!(state["next"][0]["id"], "mn-ready1");
        assert_eq!(state["decisions"][0]["id"], "mn-rule11");
        assert_eq!(state["waves"][0]["items"][0]["id"], "mn-waits1");
        let ready = state["all"]
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["id"] == "mn-ready1")
            .unwrap();
        assert_eq!(ready["dependents"], json!(["mn-waits1"]));
    }

    #[test]
    fn marker_parser_only_accepts_leading_tags() {
        let markers = vec!["[HUMAN]".to_string()];
        assert!(is_decision("[P1] [human] Rule", &markers));
        assert!(!is_decision("Mention [HUMAN] later", &markers));
        assert_eq!(strip_markers("[P1] [human] Rule"), "Rule");
    }

    #[test]
    fn identity_matching_crosses_runtime_label_forms() {
        let peers = vec![json!({"agent_id": "session-deadbeefdead"})];
        assert!(matching_peer(Some("claude-deadbeefdead0000"), &peers).is_some());
        assert!(matching_peer(Some("claude-ffffffffffff0000"), &peers).is_none());
    }

    #[test]
    fn explicit_idle_pulse_outranks_an_active_lease() {
        let peer = json!({"status": "active", "pulse": {"status": "idle"}});
        assert_eq!(attention_rank(&peer), "idle");
    }

    #[test]
    fn coord_overlay_feeds_presence_and_reranks_attention() {
        let temp = TempDir::new().unwrap();
        let coord_path = temp.path().join("coord.json");
        fs::write(
            &coord_path,
            serde_json::to_string(&json!({
                "peers": [
                    // active lease + idle pulse: the caller shipped a stale
                    // "present" rank; the core must re-rank it to idle.
                    {"agent_id": "session-deadbeefdead", "status": "active",
                     "pulse": {"status": "idle"}, "attention": "present"},
                ],
                "coord": {"claims": [{"path": "tools/x", "owner": "session-deadbeefdead"}],
                           "contention": [], "drops": [], "needs": []},
            }))
            .unwrap(),
        )
        .unwrap();
        let options = StateOptions {
            decision_markers: Vec::new(),
            agent_do: None,
            live_drift: false,
            coord_file: Some(coord_path),
        };
        let (peers, coord) = coord_overlay(&options).unwrap();
        assert_eq!(peers.len(), 1);
        assert_eq!(peers[0]["attention"], "idle");
        assert_eq!(coord["claims"][0]["path"], "tools/x");
        // Without the file, presence falls back to fetching (none here).
        let absent = StateOptions {
            coord_file: Some(temp.path().join("missing.json")),
            ..options
        };
        assert!(coord_overlay(&absent).is_none());
    }

    #[test]
    fn state_fails_closed_instead_of_dropping_a_malformed_row() {
        let temp = TempDir::new().unwrap();
        fs::create_dir(temp.path().join(".manna")).unwrap();
        fs::write(temp.path().join(".manna/sessions.jsonl"), "").unwrap();
        fs::write(
            temp.path().join(".manna/issues.jsonl"),
            "{\"id\":\"mn-broken\"}\n",
        )
        .unwrap();
        let error = derive_board_state(
            temp.path(),
            &StateOptions {
                decision_markers: Vec::new(),
                agent_do: None,
                live_drift: false,
                coord_file: None,
            },
        )
        .unwrap_err();
        assert!(error.contains("malformed board line"), "{error}");
    }
}
