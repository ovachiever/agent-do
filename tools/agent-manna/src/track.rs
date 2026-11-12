//! Tracks as whole-track build assignments.
//!
//! A track is an organizational container until it carries a sealed handoff
//! of its own. A track that does (a *dispatchable* track) can be claimed and
//! launched through the same board flow as an item: the agent that holds it
//! works the track's items one claim at a time, in dependency order, and
//! closes the track only when every item in it is done.
//!
//! Everything here is derived from the board at the moment it is asked for.
//! The track handoff never carries a progress ledger; a successor rebuilds
//! progress from these same rows.

use std::collections::{HashMap, HashSet};

use serde::Serialize;

use crate::issue::{Issue, IssueStatus, IssueType};
use crate::state::is_decision;

/// Kinds that may carry a canonical handoff: items always, tracks optionally.
/// Dreams never do.
pub fn pairable(kind: IssueType) -> bool {
    matches!(kind, IssueType::Item | IssueType::Track)
}

/// Both halves of the handoff pair are present on the row.
pub fn is_paired(issue: &Issue) -> bool {
    issue.prompt.is_some() && issue.handoff_digest.is_some()
}

/// A track carrying a sealed dispatch work order.
pub fn is_dispatchable_track(issue: &Issue) -> bool {
    issue.issue_type == IssueType::Track && is_paired(issue)
}

/// An item inside a track that another (or this) session currently holds.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct HeldChild {
    pub id: String,
    pub claimed_by: String,
}

/// An item inside a track that cannot be claimed yet because of its
/// dependencies: open blockers, blockers missing from the board, or a cycle.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct WaitingChild {
    pub id: String,
    /// Blockers that exist on the board and are not done.
    pub blocked_by: Vec<String>,
    /// Blockers no row on the board answers to; they can never clear.
    pub missing: Vec<String>,
    /// Every blocker resolves inside the waiting set itself (or depends only
    /// on rows that do), so nothing outside the cycle can ever release it.
    pub cycle: bool,
}

/// The board's answer to "what does this track still owe, and what next?".
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct TrackChildren {
    /// Items (never dreams) whose `track` edge names this track.
    pub total: usize,
    pub done: usize,
    /// Items not yet done, whatever holds them up.
    pub open: usize,
    /// Claimable now, in dispatch order: handoff priority first, then the
    /// oldest row, then the lowest id. Deterministic for a given board.
    pub eligible: Vec<String>,
    /// `eligible[0]`: the one item to claim now, or null.
    pub next: Option<String>,
    pub held: Vec<HeldChild>,
    pub waiting: Vec<WaitingChild>,
    /// Open items whose title carries a decision marker: a human's to rule
    /// on, never an agent's to claim.
    pub decisions: Vec<String>,
    /// Dreams parked in this track; visible, never claimable.
    pub dreams: usize,
    /// Items created after the track was claimed. Each carries its own sealed
    /// work order; this list exists so a change of scope is never silent.
    pub added_since_claim: Vec<String>,
    /// Why `next` is null when work remains (or when nothing exists).
    pub stall: Option<String>,
}

fn open_blockers<'a>(
    issue: &Issue,
    by_id: &HashMap<&str, &'a Issue>,
) -> (Vec<String>, Vec<String>) {
    let mut blocking = Vec::new();
    let mut missing = Vec::new();
    for blocker in &issue.blocked_by {
        match by_id.get(blocker.as_str()) {
            Some(target) if target.status == IssueStatus::Done => {}
            Some(_) => blocking.push(blocker.clone()),
            None => missing.push(blocker.clone()),
        }
    }
    (blocking, missing)
}

/// Derive a track's children summary from the whole board.
///
/// `order` is the handoff priority list (`.manna/handoff-order.yaml`, empty
/// when the board has none); `markers` are the board's decision markers.
pub fn track_children(
    issues: &[Issue],
    track: &Issue,
    order: &[String],
    markers: &[String],
) -> TrackChildren {
    let by_id: HashMap<&str, &Issue> = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect();
    let order_index: HashMap<&str, usize> = order
        .iter()
        .enumerate()
        .map(|(index, id)| (id.as_str(), index))
        .collect();
    let members: Vec<&Issue> = issues
        .iter()
        .filter(|issue| issue.id != track.id && issue.track.as_deref() == Some(track.id.as_str()))
        .collect();

    let mut summary = TrackChildren {
        total: 0,
        done: 0,
        open: 0,
        eligible: Vec::new(),
        next: None,
        held: Vec::new(),
        waiting: Vec::new(),
        decisions: Vec::new(),
        dreams: 0,
        added_since_claim: Vec::new(),
        stall: None,
    };

    let mut eligible: Vec<&Issue> = Vec::new();
    for member in &members {
        if member.issue_type == IssueType::Dream {
            summary.dreams += 1;
            continue;
        }
        if member.issue_type != IssueType::Item {
            continue;
        }
        summary.total += 1;
        if let Some(claimed_at) = track.claimed_at {
            if member.created_at > claimed_at {
                summary.added_since_claim.push(member.id.clone());
            }
        }
        if member.status == IssueStatus::Done {
            summary.done += 1;
            continue;
        }
        summary.open += 1;
        let (blocking, missing) = open_blockers(member, &by_id);
        if !blocking.is_empty() || !missing.is_empty() {
            summary.waiting.push(WaitingChild {
                id: member.id.clone(),
                blocked_by: blocking,
                missing,
                cycle: false,
            });
            continue;
        }
        if let Some(owner) = member.claimed_by.as_deref() {
            summary.held.push(HeldChild {
                id: member.id.clone(),
                claimed_by: owner.to_string(),
            });
            continue;
        }
        if member.status != IssueStatus::Open {
            // A blocked status with no live blocker, or in progress with no
            // owner: the row is inconsistent and `claim` would refuse it.
            // Report it as waiting on nothing rather than invent eligibility.
            summary.waiting.push(WaitingChild {
                id: member.id.clone(),
                blocked_by: Vec::new(),
                missing: Vec::new(),
                cycle: false,
            });
            continue;
        }
        if is_decision(&member.title, markers) {
            summary.decisions.push(member.id.clone());
            continue;
        }
        eligible.push(member);
    }

    eligible.sort_by(|left, right| {
        let left_order = order_index.get(left.id.as_str());
        let right_order = order_index.get(right.id.as_str());
        match (left_order, right_order) {
            (Some(l), Some(r)) if l != r => l.cmp(r),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            _ => left
                .created_at
                .cmp(&right.created_at)
                .then_with(|| left.id.cmp(&right.id)),
        }
    });
    summary.eligible = eligible.iter().map(|issue| issue.id.clone()).collect();
    summary.next = summary.eligible.first().cloned();

    // Cycle detection over the waiting set: peel away every row that waits
    // on something outside the set (an eligible or held sibling, an item in
    // another track, or a missing row that will never clear). Whatever
    // remains waits only on itself.
    let blockers_of: HashMap<String, Vec<String>> = summary
        .waiting
        .iter()
        .filter(|child| child.missing.is_empty())
        .map(|child| (child.id.clone(), child.blocked_by.clone()))
        .collect();
    let mut remaining: HashSet<String> = blockers_of.keys().cloned().collect();
    loop {
        let before = remaining.len();
        let peel: Vec<String> = remaining
            .iter()
            .filter(|id| {
                blockers_of[id.as_str()]
                    .iter()
                    .any(|blocker| !remaining.contains(blocker))
            })
            .cloned()
            .collect();
        for id in peel {
            remaining.remove(&id);
        }
        if remaining.len() == before {
            break;
        }
    }
    for child in &mut summary.waiting {
        child.cycle = remaining.contains(&child.id);
    }
    summary
        .waiting
        .sort_by(|left, right| left.id.cmp(&right.id));
    summary.held.sort_by(|left, right| left.id.cmp(&right.id));
    summary.decisions.sort();
    summary.added_since_claim.sort();

    if summary.next.is_none() {
        summary.stall = Some(stall_reason(&summary));
    }
    summary
}

fn stall_reason(summary: &TrackChildren) -> String {
    if summary.total == 0 {
        return "no items in this track".to_string();
    }
    if summary.open == 0 {
        return "every item is done; the track can close".to_string();
    }
    let mut reasons = Vec::new();
    if !summary.held.is_empty() {
        reasons.push(format!(
            "held by live claims: {}",
            summary
                .held
                .iter()
                .map(|child| format!("{} ({})", child.id, child.claimed_by))
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    let cycle: Vec<&str> = summary
        .waiting
        .iter()
        .filter(|child| child.cycle)
        .map(|child| child.id.as_str())
        .collect();
    if !cycle.is_empty() {
        reasons.push(format!("dependency cycle: {}", cycle.join(", ")));
    }
    let missing: Vec<String> = summary
        .waiting
        .iter()
        .filter(|child| !child.missing.is_empty())
        .map(|child| format!("{} needs missing {}", child.id, child.missing.join(", ")))
        .collect();
    if !missing.is_empty() {
        reasons.push(format!("missing dependencies: {}", missing.join("; ")));
    }
    let external: Vec<String> = summary
        .waiting
        .iter()
        .filter(|child| !child.cycle && child.missing.is_empty())
        .map(|child| {
            if child.blocked_by.is_empty() {
                format!("{} has an inconsistent status", child.id)
            } else {
                format!("{} waits on {}", child.id, child.blocked_by.join(", "))
            }
        })
        .collect();
    if !external.is_empty() {
        reasons.push(format!("waiting on blockers: {}", external.join("; ")));
    }
    if !summary.decisions.is_empty() {
        reasons.push(format!(
            "awaiting a human ruling: {}",
            summary.decisions.join(", ")
        ));
    }
    if reasons.is_empty() {
        "no eligible item".to_string()
    } else {
        reasons.join("; ")
    }
}

/// Why a track may not close right now, or `None` when it may.
///
/// A track closes only when every item in it is done. Submitted work is not
/// accepted work, so an in-progress managed item holds the track open as
/// surely as an untouched one. A track with no items has nothing to have
/// finished; delete it or give it items.
pub fn track_close_refusal(track: &Issue, issues: &[Issue]) -> Option<String> {
    if track.issue_type != IssueType::Track {
        return None;
    }
    let items: Vec<&Issue> = issues
        .iter()
        .filter(|issue| {
            issue.id != track.id
                && issue.issue_type == IssueType::Item
                && issue.track.as_deref() == Some(track.id.as_str())
        })
        .collect();
    if items.is_empty() {
        return Some(format!(
            "{} is a track with no items; nothing closes it. Add items to it, or delete it with `agent-do manna delete {}`",
            track.id, track.id
        ));
    }
    let mut open: Vec<String> = items
        .iter()
        .filter(|issue| issue.status != IssueStatus::Done)
        .map(|issue| format!("{} ({})", issue.id, issue.status))
        .collect();
    if open.is_empty() {
        return None;
    }
    open.sort();
    Some(format!(
        "{} is a track with {} open item(s): {}. A track closes only when every item in it is done; submitted work is not accepted work. Close or move the open items first",
        track.id,
        open.len(),
        open.join(", ")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{TimeZone, Utc};

    fn row(id: &str, title: &str, kind: IssueType, track: Option<&str>, day: u32) -> Issue {
        let mut issue = Issue::new(id.to_string(), title.to_string()).unwrap();
        issue.issue_type = kind;
        issue.track = track.map(str::to_string);
        issue.created_at = Utc.with_ymd_and_hms(2026, 8, day, 0, 0, 0).unwrap();
        issue.updated_at = issue.created_at;
        issue
    }

    fn markers() -> Vec<String> {
        crate::state::DEFAULT_DECISION_MARKERS
            .iter()
            .map(|marker| marker.to_string())
            .collect()
    }

    #[test]
    fn eligibility_follows_dependencies_then_priority_then_age_then_id() {
        let track = row("mn-track1", "Track", IssueType::Track, None, 1);
        let mut first = row("mn-aaaaaa", "First", IssueType::Item, Some("mn-track1"), 3);
        let mut second = row("mn-bbbbbb", "Second", IssueType::Item, Some("mn-track1"), 2);
        let mut gated = row("mn-cccccc", "Gated", IssueType::Item, Some("mn-track1"), 2);
        gated.blocked_by = vec![first.id.clone()];
        gated.status = IssueStatus::Blocked;
        let mut done = row("mn-dddddd", "Done", IssueType::Item, Some("mn-track1"), 2);
        done.status = IssueStatus::Done;
        let mut held = row("mn-eeeeee", "Held", IssueType::Item, Some("mn-track1"), 2);
        held.status = IssueStatus::InProgress;
        held.claimed_by = Some("ses-other".to_string());
        held.claim_token_hash = Some(format!("sha256:{}", "a".repeat(64)));
        let ruling = row(
            "mn-ffffff",
            "[HUMAN] Decide",
            IssueType::Item,
            Some("mn-track1"),
            2,
        );
        let dream = row("mn-dream1", "Spark", IssueType::Dream, Some("mn-track1"), 2);
        let elsewhere = row(
            "mn-999999",
            "Other track",
            IssueType::Item,
            Some("mn-track2"),
            2,
        );
        first.updated_at = Utc::now();
        second.updated_at = Utc::now();

        // Priority says second before first even though first was created later.
        let order = vec!["mn-bbbbbb".to_string(), "mn-aaaaaa".to_string()];
        let issues = vec![
            track.clone(),
            first.clone(),
            second.clone(),
            gated,
            done,
            held,
            ruling,
            dream,
            elsewhere,
        ];
        let children = track_children(&issues, &track, &order, &markers());
        assert_eq!(children.total, 6);
        assert_eq!(children.done, 1);
        assert_eq!(children.open, 5);
        assert_eq!(children.dreams, 1);
        assert_eq!(children.eligible, vec!["mn-bbbbbb", "mn-aaaaaa"]);
        assert_eq!(children.next.as_deref(), Some("mn-bbbbbb"));
        assert_eq!(children.held.len(), 1);
        assert_eq!(children.held[0].claimed_by, "ses-other");
        assert_eq!(children.waiting.len(), 1);
        assert_eq!(children.waiting[0].blocked_by, vec!["mn-aaaaaa"]);
        assert!(!children.waiting[0].cycle);
        assert_eq!(children.decisions, vec!["mn-ffffff"]);
        assert!(children.stall.is_none());

        // Without a priority list the tie falls to the older row, then the id.
        let children = track_children(&issues, &track, &[], &markers());
        assert_eq!(children.eligible, vec!["mn-bbbbbb", "mn-aaaaaa"]);
        let mut same_day = second.clone();
        same_day.created_at = first.created_at;
        let issues = vec![track.clone(), first, same_day];
        let children = track_children(&issues, &track, &[], &markers());
        assert_eq!(children.eligible, vec!["mn-aaaaaa", "mn-bbbbbb"]);
    }

    #[test]
    fn stalls_name_the_reason_and_cycles_are_found() {
        let mut track = row("mn-track1", "Track", IssueType::Track, None, 1);
        let mut a = row("mn-aaaaaa", "A", IssueType::Item, Some("mn-track1"), 2);
        let mut b = row("mn-bbbbbb", "B", IssueType::Item, Some("mn-track1"), 2);
        a.blocked_by = vec![b.id.clone()];
        b.blocked_by = vec![a.id.clone()];
        a.status = IssueStatus::Blocked;
        b.status = IssueStatus::Blocked;
        let mut c = row("mn-cccccc", "C", IssueType::Item, Some("mn-track1"), 2);
        c.blocked_by = vec!["mn-missing".to_string()];
        c.status = IssueStatus::Blocked;
        let mut d = row("mn-dddddd", "D", IssueType::Item, Some("mn-track1"), 2);
        d.blocked_by = vec!["mn-outside".to_string()];
        d.status = IssueStatus::Blocked;
        let outside = row("mn-outside", "Outside", IssueType::Item, None, 2);
        let mut held = row("mn-eeeeee", "Held", IssueType::Item, Some("mn-track1"), 2);
        held.status = IssueStatus::InProgress;
        held.claimed_by = Some("ses-other".to_string());
        held.claim_token_hash = Some(format!("sha256:{}", "a".repeat(64)));
        // Claimed on the 3rd: every day-2 row predates the claim, only the
        // day-5 row was added since.
        track.claimed_at = Some(Utc.with_ymd_and_hms(2026, 8, 3, 12, 0, 0).unwrap());
        let late = row("mn-ffffff", "Late", IssueType::Item, Some("mn-track1"), 5);
        let mut late = late;
        late.status = IssueStatus::InProgress;
        late.claimed_by = Some("ses-late".to_string());
        late.claim_token_hash = Some(format!("sha256:{}", "b".repeat(64)));

        let issues = vec![track.clone(), a, b, c, d, outside, held, late];
        let children = track_children(&issues, &track, &[], &markers());
        assert!(children.next.is_none());
        let waiting: HashMap<&str, &WaitingChild> = children
            .waiting
            .iter()
            .map(|child| (child.id.as_str(), child))
            .collect();
        assert!(waiting["mn-aaaaaa"].cycle);
        assert!(waiting["mn-bbbbbb"].cycle);
        assert!(!waiting["mn-cccccc"].cycle);
        assert_eq!(waiting["mn-cccccc"].missing, vec!["mn-missing"]);
        assert!(!waiting["mn-dddddd"].cycle);
        assert_eq!(waiting["mn-dddddd"].blocked_by, vec!["mn-outside"]);
        let stall = children.stall.unwrap();
        assert!(
            stall.contains("held by live claims: mn-eeeeee (ses-other), mn-ffffff (ses-late)"),
            "{stall}"
        );
        assert!(
            stall.contains("dependency cycle: mn-aaaaaa, mn-bbbbbb"),
            "{stall}"
        );
        assert!(
            stall.contains("missing dependencies: mn-cccccc needs missing mn-missing"),
            "{stall}"
        );
        assert!(
            stall.contains("waiting on blockers: mn-dddddd waits on mn-outside"),
            "{stall}"
        );
        assert_eq!(children.added_since_claim, vec!["mn-ffffff"]);
    }

    #[test]
    fn empty_and_finished_tracks_say_so() {
        let track = row("mn-track1", "Track", IssueType::Track, None, 1);
        let children = track_children(&[track.clone()], &track, &[], &markers());
        assert_eq!(children.total, 0);
        assert_eq!(children.stall.as_deref(), Some("no items in this track"));
        let mut done = row("mn-aaaaaa", "A", IssueType::Item, Some("mn-track1"), 2);
        done.status = IssueStatus::Done;
        let children = track_children(&[track.clone(), done], &track, &[], &markers());
        assert_eq!(children.open, 0);
        assert_eq!(
            children.stall.as_deref(),
            Some("every item is done; the track can close")
        );
    }

    #[test]
    fn close_refusal_names_open_items_and_empty_tracks() {
        let track = row("mn-track1", "Track", IssueType::Track, None, 1);
        let refusal = track_close_refusal(&track, &[track.clone()]).unwrap();
        assert!(refusal.contains("no items"), "{refusal}");
        let mut open = row("mn-aaaaaa", "A", IssueType::Item, Some("mn-track1"), 2);
        open.status = IssueStatus::InProgress;
        open.claimed_by = Some("ses-worker".to_string());
        open.claim_token_hash = Some(format!("sha256:{}", "a".repeat(64)));
        let mut done = row("mn-bbbbbb", "B", IssueType::Item, Some("mn-track1"), 2);
        done.status = IssueStatus::Done;
        let dream = row("mn-dream1", "Spark", IssueType::Dream, Some("mn-track1"), 2);
        let issues = vec![track.clone(), open.clone(), done.clone(), dream.clone()];
        let refusal = track_close_refusal(&track, &issues).unwrap();
        assert!(
            refusal.contains("1 open item(s): mn-aaaaaa (in_progress)"),
            "{refusal}"
        );
        open.status = IssueStatus::Done;
        let issues = vec![track.clone(), open, done, dream];
        assert!(track_close_refusal(&track, &issues).is_none());
        let item = row("mn-cccccc", "Not a track", IssueType::Item, None, 2);
        assert!(track_close_refusal(&item, &issues).is_none());
    }

    #[test]
    fn pairing_predicates() {
        assert!(pairable(IssueType::Item));
        assert!(pairable(IssueType::Track));
        assert!(!pairable(IssueType::Dream));
        let mut track = row("mn-track1", "Track", IssueType::Track, None, 1);
        assert!(!is_paired(&track));
        assert!(!is_dispatchable_track(&track));
        track.prompt = Some(".handoff/mn-track1-track.md".to_string());
        assert!(!is_paired(&track));
        track.handoff_digest = Some(format!("sha256:{}", "a".repeat(64)));
        assert!(is_paired(&track));
        assert!(is_dispatchable_track(&track));
    }
}
