//! Board grammar checks: lint rules and reconcile drift detection.
//!
//! Pure functions over loaded issues. The CLI layer owns all shelling out
//! (git, process probes, coord) and passes results in, so every check here
//! is unit-testable without a live environment.

use std::collections::HashMap;

use chrono::{DateTime, Duration, Utc};
use serde::Serialize;

use crate::issue::{Issue, IssueStatus, IssueType, LegacyMigrationDisposition};

/// Drift finding kinds, pinned by the `.manna/drift.yaml` contract.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FindingKind {
    LandedOpen,
    DeadClaim,
    BlockerDesync,
    StaleDream,
    DanglingTrack,
    FederationIntegrity,
    DocReference,
    PromptPairing,
    HandoffPresentation,
    WorkflowSprawl,
    OrphanHandoff,
    Skipped,
}

impl FindingKind {
    /// Every kind, in declaration order (for --only's error text).
    pub const ALL: [FindingKind; 12] = [
        FindingKind::LandedOpen,
        FindingKind::DeadClaim,
        FindingKind::BlockerDesync,
        FindingKind::StaleDream,
        FindingKind::DanglingTrack,
        FindingKind::FederationIntegrity,
        FindingKind::DocReference,
        FindingKind::PromptPairing,
        FindingKind::HandoffPresentation,
        FindingKind::WorkflowSprawl,
        FindingKind::OrphanHandoff,
        FindingKind::Skipped,
    ];

    /// The snake_case name the drift contract writes.
    pub fn name(self) -> &'static str {
        match self {
            FindingKind::LandedOpen => "landed_open",
            FindingKind::DeadClaim => "dead_claim",
            FindingKind::BlockerDesync => "blocker_desync",
            FindingKind::StaleDream => "stale_dream",
            FindingKind::DanglingTrack => "dangling_track",
            FindingKind::FederationIntegrity => "federation_integrity",
            FindingKind::DocReference => "doc_reference",
            FindingKind::PromptPairing => "prompt_pairing",
            FindingKind::HandoffPresentation => "handoff_presentation",
            FindingKind::WorkflowSprawl => "workflow_sprawl",
            FindingKind::OrphanHandoff => "orphan_handoff",
            FindingKind::Skipped => "skipped",
        }
    }

    pub fn from_name(name: &str) -> Option<FindingKind> {
        FindingKind::ALL.iter().copied().find(|kind| kind.name() == name)
    }
}

/// One reconcile finding, shaped for `.manna/drift.yaml`.
#[derive(Debug, Clone, Serialize)]
pub struct Finding {
    pub kind: FindingKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub issue_id: Option<String>,
    pub detail: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proposed_fix: Option<String>,
}

impl Finding {
    /// A `skipped` finding recording why a check could not run.
    pub fn skipped(check: &str, reason: &str) -> Self {
        Finding {
            kind: FindingKind::Skipped,
            issue_id: None,
            detail: format!("{} skipped: {}", check, reason),
            evidence: None,
            proposed_fix: None,
        }
    }
}

/// One lint finding: a board-grammar violation on a single issue.
#[derive(Debug, Clone, Serialize)]
pub struct LintFinding {
    pub issue_id: String,
    pub rule: String,
    pub detail: String,
}

/// True when `s` is exactly `mn-` + 6 lowercase hex chars.
pub fn is_manna_id(s: &str) -> bool {
    s.len() == 9
        && s.starts_with("mn-")
        && s.bytes()
            .skip(3)
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// Extract `Manna: mn-xxxxxx` trailer IDs from a commit body.
///
/// A trailer is a body line that is exactly `Manna: <id>` (key case-sensitive,
/// one ID per line, multiple lines allowed).
pub fn manna_trailer_ids(body: &str) -> Vec<String> {
    body.lines()
        .filter_map(|line| {
            let rest = line.strip_prefix("Manna: ")?;
            is_manna_id(rest).then(|| rest.to_string())
        })
        .collect()
}

/// Extract every `mn-[a-f0-9]{6}` occurrence from a line of text.
///
/// Requires a non-hex character (or end of line) after the sixth hex char so
/// longer hex runs are not truncated into false IDs.
pub fn extract_manna_ids(line: &str) -> Vec<String> {
    let bytes = line.as_bytes();
    let mut ids = Vec::new();
    let mut start = 0;
    while let Some(pos) = line[start..].find("mn-") {
        let candidate_start = start + pos;
        let candidate_end = candidate_start + 9;
        // candidate_end can land inside a multibyte char (e.g. "mn-abcd☉x");
        // slicing there panics, so it cannot be a valid id at all.
        if candidate_end <= bytes.len()
            && line.is_char_boundary(candidate_end)
            && is_manna_id(&line[candidate_start..candidate_end])
        {
            let followed_by_hex = bytes
                .get(candidate_end)
                .is_some_and(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'));
            if !followed_by_hex {
                ids.push(line[candidate_start..candidate_end].to_string());
            }
        }
        start = candidate_start + 3;
    }
    ids
}

/// Extract issue ids targeted by claim commands in a prompt file's text.
///
/// A claim command is any line containing `manna claim <id>` — the invocation
/// prefix is free (`agent-do manna claim`, an absolute-path binary, an env-var
/// pin like `MANNA_SESSION_ID=... agent-do manna claim`). The id must follow
/// `manna claim ` immediately, with the same boundary rule as
/// `extract_manna_ids`; multiple claim commands per file are allowed.
pub fn claim_command_ids(text: &str) -> Vec<String> {
    const NEEDLE: &str = "manna claim ";
    let mut ids = Vec::new();
    for line in text.lines() {
        let bytes = line.as_bytes();
        let mut start = 0;
        while let Some(pos) = line[start..].find(NEEDLE) {
            let id_start = start + pos + NEEDLE.len();
            let id_end = id_start + 9;
            // Same boundary guard as extract_manna_ids: a multibyte char inside
            // the 9-byte window means no valid id and must not panic the slice.
            if id_end <= bytes.len()
                && line.is_char_boundary(id_end)
                && is_manna_id(&line[id_start..id_end])
            {
                let followed_by_hex = bytes
                    .get(id_end)
                    .is_some_and(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'));
                if !followed_by_hex {
                    ids.push(line[id_start..id_end].to_string());
                }
            }
            start = start + pos + NEEDLE.len();
        }
    }
    ids
}

/// Resolve an issue's work-order prompt pointer.
///
/// The `prompt` field wins; otherwise a description whose FIRST line is
/// `PROMPT: <path>` (the blessed interim convention) supplies it. Historical
/// descriptions may append ` — <note>` after the path; that prose is context,
/// never part of the filename. Both sources are trimmed; an empty pointer is
/// no pointer.
pub fn strip_prompt_annotation(pointer: &str) -> &str {
    pointer
        .split_once(" — ")
        .map_or(pointer, |(path, _)| path)
        .trim()
}

pub fn prompt_pointer(issue: &Issue) -> Option<String> {
    if let Some(field) = issue
        .prompt
        .as_deref()
        .map(str::trim)
        .filter(|p| !p.is_empty())
    {
        return Some(field.to_string());
    }
    let first_line = issue.description.as_deref()?.lines().next()?.trim();
    let path = first_line.strip_prefix("PROMPT:")?.trim();
    let path = strip_prompt_annotation(path);
    (!path.is_empty()).then(|| path.to_string())
}

/// Parse a pid out of the pre-authentication `ses_pid{pid}_{ts}` legacy format.
pub fn parse_session_pid(session_id: &str) -> Option<u32> {
    let rest = session_id.strip_prefix("ses_pid")?;
    let (pid, ts) = rest.split_once('_')?;
    if pid.is_empty() || ts.is_empty() {
        return None;
    }
    if !pid.bytes().all(|b| b.is_ascii_digit()) || !ts.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    pid.parse().ok()
}

/// landed_open: issues referenced by landed commit trailers but not yet done.
///
/// `landed` maps issue ID -> commit SHAs whose bodies carry its trailer.
/// Report-only: merge judgment stays with the human/orchestrator.
pub fn check_landed_open(issues: &[Issue], landed: &HashMap<String, Vec<String>>) -> Vec<Finding> {
    let mut findings = Vec::new();
    for issue in issues {
        if issue.status == IssueStatus::Done {
            continue;
        }
        if let Some(shas) = landed.get(&issue.id) {
            let mut evidence: Vec<String> = shas
                .iter()
                .take(3)
                .map(|s| s.chars().take(12).collect())
                .collect();
            if shas.len() > 3 {
                evidence.push(format!("+{} more", shas.len() - 3));
            }
            findings.push(Finding {
                kind: FindingKind::LandedOpen,
                issue_id: Some(issue.id.clone()),
                detail: format!(
                    "referenced by landed commit trailer but status is {}",
                    issue.status
                ),
                evidence: Some(evidence.join(", ")),
                proposed_fix: Some(format!(
                    "review the commits; if the work landed, claim and done {}",
                    issue.id
                )),
            });
        }
    }
    findings
}

/// blocker_desync: blocked status out of sync with the blocked_by list.
///
/// Backstop for deleted blockers, older binaries, and hand-edited boards;
/// `done` releases its dependents inline. A blocker counts as resolved when
/// it is done or no longer exists on the board.
pub fn check_blocker_desync(issues: &[Issue]) -> Vec<Finding> {
    let by_id: HashMap<&str, &Issue> = issues.iter().map(|i| (i.id.as_str(), i)).collect();
    let mut findings = Vec::new();
    for issue in issues {
        if issue.status != IssueStatus::Blocked {
            continue;
        }
        if issue.blocked_by.is_empty() {
            findings.push(Finding {
                kind: FindingKind::BlockerDesync,
                issue_id: Some(issue.id.clone()),
                detail: "status blocked but blocked_by is empty".to_string(),
                evidence: None,
                proposed_fix: Some("recompute status from blocked_by".to_string()),
            });
            continue;
        }
        let states: Vec<String> = issue
            .blocked_by
            .iter()
            .map(|b| match by_id.get(b.as_str()) {
                Some(blocker) => format!("{} ({})", b, blocker.status),
                None => format!("{} (missing)", b),
            })
            .collect();
        let all_resolved = issue.blocked_by.iter().all(|b| {
            by_id
                .get(b.as_str())
                .is_none_or(|blocker| blocker.status == IssueStatus::Done)
        });
        if all_resolved {
            findings.push(Finding {
                kind: FindingKind::BlockerDesync,
                issue_id: Some(issue.id.clone()),
                detail: "all blockers resolved but status is still blocked".to_string(),
                evidence: Some(states.join(", ")),
                proposed_fix: Some("remove resolved blockers to unblock".to_string()),
            });
        }
    }
    findings
}

/// stale_dream: open dreams older than `age_days` (clock injected for tests).
pub fn check_stale_dream(issues: &[Issue], now: DateTime<Utc>, age_days: i64) -> Vec<Finding> {
    issues
        .iter()
        .filter(|i| {
            i.issue_type == IssueType::Dream
                && i.status == IssueStatus::Open
                && now - i.created_at > Duration::days(age_days)
        })
        .map(|i| Finding {
            kind: FindingKind::StaleDream,
            issue_id: Some(i.id.clone()),
            detail: format!("open dream older than {} days", age_days),
            evidence: Some(format!("created_at {}", i.created_at.format("%Y-%m-%d"))),
            proposed_fix: Some("promote to an item on a track, or close it".to_string()),
        })
        .collect()
}

/// dangling_track: track edges pointing at missing IDs or non-track rows.
pub fn check_dangling_track(issues: &[Issue]) -> Vec<Finding> {
    let by_id: HashMap<&str, &Issue> = issues.iter().map(|i| (i.id.as_str(), i)).collect();
    let mut findings = Vec::new();
    for issue in issues {
        if let Some(track_id) = &issue.track {
            let problem = match by_id.get(track_id.as_str()) {
                None => Some("track edge points at a missing issue".to_string()),
                Some(target) if target.issue_type != IssueType::Track => Some(format!(
                    "track edge points at a non-track issue (type: {})",
                    target.issue_type
                )),
                Some(_) => None,
            };
            if let Some(detail) = problem {
                findings.push(Finding {
                    kind: FindingKind::DanglingTrack,
                    issue_id: Some(issue.id.clone()),
                    detail,
                    evidence: Some(track_id.clone()),
                    proposed_fix: Some("repoint or clear the track edge".to_string()),
                });
            }
        }
    }
    findings
}

/// Lint the whole board: per-issue validate() plus the grammar rules.
///
/// Rules: (a) items need a track once the board has any tracks (young boards
/// don't nag); (b) track edges must point at existing track rows; (c) dreams
/// only carry status open or done.
pub fn lint_board(issues: &[Issue]) -> Vec<LintFinding> {
    let has_tracks = issues.iter().any(|i| i.issue_type == IssueType::Track);
    let by_id: HashMap<&str, &Issue> = issues.iter().map(|i| (i.id.as_str(), i)).collect();
    let mut findings = Vec::new();

    for issue in issues {
        if let Err(e) = issue.validate() {
            findings.push(LintFinding {
                issue_id: issue.id.clone(),
                rule: "validate".to_string(),
                detail: e,
            });
        }

        let grandfathered_history = issue
            .legacy_migration
            .as_ref()
            .is_some_and(|migration| migration.disposition == LegacyMigrationDisposition::History);
        if has_tracks
            && issue.issue_type == IssueType::Item
            && issue.track.is_none()
            && !grandfathered_history
        {
            findings.push(LintFinding {
                issue_id: issue.id.clone(),
                rule: "untracked_item".to_string(),
                detail: "item has no track on a board with tracks".to_string(),
            });
        }

        if let Some(track_id) = &issue.track {
            let problem = match by_id.get(track_id.as_str()) {
                None => Some(format!("track edge points at missing issue {}", track_id)),
                Some(target) if target.issue_type != IssueType::Track => Some(format!(
                    "track edge points at non-track issue {} (type: {})",
                    track_id, target.issue_type
                )),
                Some(_) => None,
            };
            if let Some(detail) = problem {
                findings.push(LintFinding {
                    issue_id: issue.id.clone(),
                    rule: "dangling_track".to_string(),
                    detail,
                });
            }
        }

        if issue.issue_type == IssueType::Dream
            && issue.status != IssueStatus::Open
            && issue.status != IssueStatus::Done
        {
            findings.push(LintFinding {
                issue_id: issue.id.clone(),
                rule: "dream_status".to_string(),
                detail: format!("dream has status {}, expected open or done", issue.status),
            });
        }
    }

    findings
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::issue::SessionIdentity;

    fn session(id: &str) -> SessionIdentity {
        SessionIdentity::from_token(id, &format!("{}-0123456789abcdef0123456789abcdef", id))
            .unwrap()
    }

    fn issue(id: &str, title: &str) -> Issue {
        Issue::new(id.to_string(), title.to_string()).unwrap()
    }

    fn track(id: &str, title: &str) -> Issue {
        let mut i = issue(id, title);
        i.issue_type = IssueType::Track;
        i
    }

    fn dream(id: &str, title: &str) -> Issue {
        let mut i = issue(id, title);
        i.issue_type = IssueType::Dream;
        i
    }

    #[test]
    fn multibyte_inside_id_window_does_not_panic() {
        // 9-byte window ends inside '☉' (3 bytes) — must reject, not panic.
        assert!(extract_manna_ids("mn-abcd☉x").is_empty());
        assert!(claim_command_ids("agent-do manna claim mn-abcd☉x").is_empty());
        // The real-world trigger: U+FFFD replacement chars from lossy reads.
        assert!(extract_manna_ids("mn-ab\u{FFFD}cdef").is_empty());
        // A valid id after multibyte prose still parses.
        assert_eq!(
            extract_manna_ids("☉ glyphs then mn-abc123 ok"),
            vec!["mn-abc123"]
        );
    }

    // ── ID and trailer parsing ──────────────────────────────────────────

    #[test]
    fn test_is_manna_id() {
        assert!(is_manna_id("mn-abc123"));
        assert!(is_manna_id("mn-000fff"));
        assert!(!is_manna_id("mn-ABC123")); // uppercase is not an ID
        assert!(!is_manna_id("mn-xyz123")); // non-hex
        assert!(!is_manna_id("mn-abc12")); // too short
        assert!(!is_manna_id("mn-abc1234")); // too long
        assert!(!is_manna_id("nm-abc123"));
    }

    #[test]
    fn test_manna_trailer_ids() {
        let body = "Fix the thing\n\nManna: mn-abc123\nManna: mn-def456\n";
        assert_eq!(manna_trailer_ids(body), vec!["mn-abc123", "mn-def456"]);
    }

    #[test]
    fn test_manna_trailer_rejects_inexact_lines() {
        // Key is case-sensitive; the line must be exactly `Manna: <id>`.
        let body = "manna: mn-abc123\nManna:mn-abc123\nManna: mn-abc123 done\nSee Manna: mn-abc123";
        assert!(manna_trailer_ids(body).is_empty());
    }

    #[test]
    fn test_extract_manna_ids() {
        assert_eq!(
            extract_manna_ids("see mn-abc123 and (mn-def456)."),
            vec!["mn-abc123", "mn-def456"]
        );
        // Longer hex run is not an ID.
        assert!(extract_manna_ids("hash mn-abc1234def").is_empty());
        // Non-hex chars stop the match.
        assert!(extract_manna_ids("mn-xxxxxx placeholder").is_empty());
    }

    #[test]
    fn test_claim_command_ids_tolerates_any_invocation_prefix() {
        let text = "# Lane 4\n\
                    **Claim first:** `MANNA_SESSION_ID=lane-pairing agent-do manna claim mn-91dc30`\n\
                    /abs/path/agent-do manna claim mn-abc123 && echo claimed\n\
                    bare mention mn-def456 is data, not a claim\n\
                    Manna: mn-0fff00\n";
        assert_eq!(claim_command_ids(text), vec!["mn-91dc30", "mn-abc123"]);
    }

    #[test]
    fn test_claim_command_ids_multiple_per_line() {
        let line = "agent-do manna claim mn-aaa111 && agent-do manna claim mn-bbb222";
        assert_eq!(claim_command_ids(line), vec!["mn-aaa111", "mn-bbb222"]);
    }

    #[test]
    fn test_claim_command_ids_rejects_inexact() {
        // The id must follow `manna claim ` immediately and be a valid id.
        assert!(claim_command_ids("manna claim mn-abc1234def").is_empty()); // longer hex run
        assert!(claim_command_ids("manna claim mn-xyz123").is_empty()); // non-hex
        assert!(claim_command_ids("manna claimmn-abc123").is_empty()); // missing space
        assert!(claim_command_ids("manna claim  mn-abc123").is_empty()); // double space
        assert!(claim_command_ids("manna show mn-abc123").is_empty()); // other verb
    }

    #[test]
    fn test_parse_session_pid() {
        assert_eq!(parse_session_pid("ses_pid1234_1750000000"), Some(1234));
        assert_eq!(parse_session_pid("ses_test_99"), None);
        assert_eq!(parse_session_pid("ses_pid_1750000000"), None);
        assert_eq!(parse_session_pid("ses_pid12ab_1750000000"), None);
        assert_eq!(parse_session_pid("session-4e458bf7ce7d"), None);
    }

    // ── prompt_pointer ──────────────────────────────────────────────────

    #[test]
    fn test_prompt_pointer_field_wins_over_description() {
        let mut i = issue("mn-aaa111", "Prompted");
        i.prompt = Some("  /field/path.md  ".to_string());
        i.description = Some("PROMPT: /desc/path.md\nbody".to_string());
        assert_eq!(prompt_pointer(&i).as_deref(), Some("/field/path.md"));
    }

    #[test]
    fn test_prompt_pointer_from_description_first_line() {
        let mut i = issue("mn-aaa111", "Prompted");
        i.description = Some("PROMPT:   /desc/path.md \nmore detail".to_string());
        assert_eq!(prompt_pointer(&i).as_deref(), Some("/desc/path.md"));

        i.description = Some("PROMPT: /desc/path.md — read this before starting\nbody".to_string());
        assert_eq!(prompt_pointer(&i).as_deref(), Some("/desc/path.md"));
    }

    #[test]
    fn test_prompt_pointer_ignores_non_first_lines_and_empty() {
        let mut i = issue("mn-aaa111", "Unprompted");
        assert_eq!(prompt_pointer(&i), None);
        // The convention binds only on the FIRST description line.
        i.description = Some("context first\nPROMPT: /desc/path.md".to_string());
        assert_eq!(prompt_pointer(&i), None);
        // An empty pointer is no pointer, from either source.
        i.description = Some("PROMPT:   ".to_string());
        assert_eq!(prompt_pointer(&i), None);
        i.prompt = Some("   ".to_string());
        assert_eq!(prompt_pointer(&i), None);
    }

    // ── landed_open ─────────────────────────────────────────────────────

    #[test]
    fn test_check_landed_open() {
        let mut done = issue("mn-aaa111", "Landed and closed");
        done.claim(&session("ses_x")).unwrap();
        done.complete(&session("ses_x")).unwrap();
        let open = issue("mn-bbb222", "Landed but open");
        let untouched = issue("mn-ccc333", "Never landed");

        let mut landed = HashMap::new();
        landed.insert("mn-aaa111".to_string(), vec!["sha1".to_string()]);
        landed.insert(
            "mn-bbb222".to_string(),
            vec!["sha2".to_string(), "sha3".to_string()],
        );

        let findings = check_landed_open(&[done, open, untouched], &landed);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].kind, FindingKind::LandedOpen);
        assert_eq!(findings[0].issue_id.as_deref(), Some("mn-bbb222"));
        assert!(findings[0].evidence.as_deref().unwrap().contains("sha2"));
    }

    // ── blocker_desync ──────────────────────────────────────────────────

    #[test]
    fn test_blocker_desync_all_done() {
        let mut blocker = issue("mn-aaa111", "Blocker");
        blocker.claim(&session("ses_x")).unwrap();
        blocker.complete(&session("ses_x")).unwrap();
        let mut blocked = issue("mn-bbb222", "Blocked");
        blocked.add_blocker("mn-aaa111".to_string());
        assert_eq!(blocked.status, IssueStatus::Blocked);

        let findings = check_blocker_desync(&[blocker, blocked]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].kind, FindingKind::BlockerDesync);
        assert_eq!(findings[0].issue_id.as_deref(), Some("mn-bbb222"));
    }

    #[test]
    fn test_blocker_desync_missing_blocker_counts_resolved() {
        let mut blocked = issue("mn-bbb222", "Blocked by ghost");
        blocked.add_blocker("mn-404404".to_string());

        let findings = check_blocker_desync(&[blocked]);
        assert_eq!(findings.len(), 1);
        assert!(findings[0].evidence.as_deref().unwrap().contains("missing"));
    }

    #[test]
    fn test_blocker_desync_empty_blocked_by() {
        let mut stuck = issue("mn-bbb222", "Stuck");
        stuck.status = IssueStatus::Blocked;

        let findings = check_blocker_desync(&[stuck]);
        assert_eq!(findings.len(), 1);
        assert!(findings[0].detail.contains("blocked_by is empty"));
    }

    #[test]
    fn test_blocker_desync_live_blocker_is_clean() {
        let blocker = issue("mn-aaa111", "Still open");
        let mut blocked = issue("mn-bbb222", "Blocked");
        blocked.add_blocker("mn-aaa111".to_string());

        assert!(check_blocker_desync(&[blocker, blocked]).is_empty());
    }

    // ── stale_dream ─────────────────────────────────────────────────────

    #[test]
    fn test_stale_dream_with_injected_clock() {
        let mut old_dream = dream("mn-aaa111", "Old spark");
        old_dream.created_at = Utc::now() - Duration::days(30);
        let fresh_dream = dream("mn-bbb222", "Fresh spark");
        let mut done_dream = dream("mn-ccc333", "Resolved spark");
        done_dream.created_at = Utc::now() - Duration::days(30);
        done_dream.status = IssueStatus::Done;
        let mut old_item = issue("mn-ddd444", "Old item");
        old_item.created_at = Utc::now() - Duration::days(30);

        let now = Utc::now();
        let findings = check_stale_dream(&[old_dream, fresh_dream, done_dream, old_item], now, 14);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].kind, FindingKind::StaleDream);
        assert_eq!(findings[0].issue_id.as_deref(), Some("mn-aaa111"));
    }

    #[test]
    fn test_stale_dream_threshold_boundary() {
        let mut d = dream("mn-aaa111", "Edge spark");
        let now = Utc::now();
        d.created_at = now - Duration::days(14);
        // Exactly at the threshold is not yet stale (strictly older-than).
        assert!(check_stale_dream(&[d.clone()], now, 14).is_empty());
        d.created_at = now - Duration::days(15);
        assert_eq!(check_stale_dream(&[d], now, 14).len(), 1);
    }

    // ── dangling_track ──────────────────────────────────────────────────

    #[test]
    fn test_dangling_track_missing_and_nontrack() {
        let t = track("mn-aaa111", "Real track");
        let mut fine = issue("mn-bbb222", "On the track");
        fine.track = Some("mn-aaa111".to_string());
        let mut ghost = issue("mn-ccc333", "Ghost edge");
        ghost.track = Some("mn-404404".to_string());
        let mut wrong = issue("mn-ddd444", "Edge to item");
        wrong.track = Some("mn-bbb222".to_string());

        let findings = check_dangling_track(&[t, fine, ghost, wrong]);
        assert_eq!(findings.len(), 2);
        assert_eq!(findings[0].issue_id.as_deref(), Some("mn-ccc333"));
        assert!(findings[0].detail.contains("missing"));
        assert_eq!(findings[1].issue_id.as_deref(), Some("mn-ddd444"));
        assert!(findings[1].detail.contains("non-track"));
    }

    // ── lint ────────────────────────────────────────────────────────────

    #[test]
    fn test_lint_clean_young_board() {
        // No tracks yet: untracked items don't nag (bootstrap-friendly).
        let a = issue("mn-aaa111", "Item one");
        let b = issue("mn-bbb222", "Item two");
        assert!(lint_board(&[a, b]).is_empty());
    }

    #[test]
    fn test_lint_untracked_item_once_board_has_tracks() {
        let t = track("mn-aaa111", "Track");
        let mut tracked = issue("mn-bbb222", "Tracked");
        tracked.track = Some("mn-aaa111".to_string());
        let loose = issue("mn-ccc333", "Loose item");

        let findings = lint_board(&[t, tracked, loose]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule, "untracked_item");
        assert_eq!(findings[0].issue_id, "mn-ccc333");
    }

    #[test]
    fn test_lint_grandfathers_untracked_legacy_history() {
        let t = track("mn-aaa111", "Track");
        let mut history = issue("mn-bbb222", "Legacy history");
        history.status = IssueStatus::Done;
        history.legacy_migration = Some(crate::issue::LegacyMigrationAnnotation {
            version: 1,
            disposition: LegacyMigrationDisposition::History,
            migrated_at: Utc::now(),
            previous_prompt: Some(".dev/session-prompts/old.md".to_string()),
            released_claimed_by: None,
        });
        assert!(lint_board(&[t, history]).is_empty());
    }

    #[test]
    fn test_lint_untracked_dream_is_fine() {
        let t = track("mn-aaa111", "Track");
        let mut tracked = issue("mn-bbb222", "Tracked");
        tracked.track = Some("mn-aaa111".to_string());
        let d = dream("mn-ccc333", "Floating spark");
        assert!(lint_board(&[t, tracked, d]).is_empty());
    }

    #[test]
    fn test_lint_dangling_track_edge() {
        let mut ghost = issue("mn-aaa111", "Ghost edge");
        ghost.track = Some("mn-404404".to_string());
        let findings = lint_board(&[ghost]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule, "dangling_track");
    }

    #[test]
    fn test_lint_dream_status() {
        // claim() now refuses dreams, so an in_progress dream can only arrive
        // from outside the CLI (a hand-edited board, an older binary). Lint is
        // what catches that residue, so the state is set directly here.
        let mut d = dream("mn-aaa111", "Claimed dream");
        d.status = IssueStatus::InProgress;
        d.claimed_by = Some("ses_x".to_string());
        d.claimed_at = Some(Utc::now());
        d.claim_token_hash = Some(format!("sha256:{}", "a".repeat(64)));
        let findings = lint_board(&[d]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule, "dream_status");
        assert!(findings[0].detail.contains("in_progress"));
    }

    #[test]
    fn test_lint_validate_rule() {
        let mut broken = issue("mn-aaa111", "Broken");
        broken.status = IssueStatus::InProgress; // in_progress without claimed_by
        let findings = lint_board(&[broken]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule, "validate");
    }

    #[test]
    fn test_finding_skipped_shape() {
        let f = Finding::skipped("landed_open", "not a git repository");
        assert_eq!(f.kind, FindingKind::Skipped);
        assert_eq!(f.detail, "landed_open skipped: not a git repository");
    }

    #[test]
    fn test_finding_kind_serializes_snake_case() {
        let f = Finding {
            kind: FindingKind::BlockerDesync,
            issue_id: Some("mn-aaa111".to_string()),
            detail: "d".to_string(),
            evidence: None,
            proposed_fix: None,
        };
        let yaml = serde_yaml::to_string(&f).unwrap();
        assert!(yaml.contains("kind: blocker_desync"));
        assert!(!yaml.contains("evidence"));
    }

    #[test]
    fn test_prompt_pairing_kind_serializes_snake_case() {
        let f = Finding {
            kind: FindingKind::PromptPairing,
            issue_id: Some("mn-aaa111".to_string()),
            detail: "d".to_string(),
            evidence: None,
            proposed_fix: None,
        };
        let yaml = serde_yaml::to_string(&f).unwrap();
        assert!(yaml.contains("kind: prompt_pairing"));
    }
}
