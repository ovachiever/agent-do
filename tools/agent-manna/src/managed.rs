//! Managed lifecycle: scoped coordinator grants, worker submissions, recorded
//! acceptance, and closure assessment for items whose completion is owned by
//! a coordinator rather than by the worker that built them.
//!
//! Storage, beside the board and written under the same board lock:
//! - `.manna/coordinators.json`: explicit grants (who may coordinate what)
//! - `.manna/managed.json`: per-item managed records (attempt, required
//!   checks, submission, acceptances, releases, pinned integration target)
//! - `.manna/lifecycle.jsonl`: append-only audit of every managed action
//!
//! These files are sidecars on purpose. `issues.jsonl` rows are the strict
//! transactional spine that older binaries, the pair journal, and recovery
//! all compare byte-for-byte; a sidecar leaves every one of those unchanged,
//! an older binary never strips a field it does not know, and an unmanaged
//! board never acquires the files at all. The rule they enforce lives in
//! this module so `done`, `reconcile --fix`, and any later mutation path can
//! ask the same question: is this item's closure authorized right now?

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::issue::{Issue, IssueStatus, SessionIdentity};

pub const COORDINATORS_FILE: &str = "coordinators.json";
pub const MANAGED_FILE: &str = "managed.json";
pub const LIFECYCLE_FILE: &str = "lifecycle.jsonl";

/// The capability name an adoption check looks for. A binary that compiles
/// this module reports it; a binary that does not cannot be asked.
pub const CAPABILITY: &str = "managed_lifecycle";

// ----------------------------------------------------------------------------
// Grants
// ----------------------------------------------------------------------------

/// What a grant covers: explicit item ids and/or whole tracks.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrantScope {
    #[serde(default)]
    pub items: Vec<String>,
    #[serde(default)]
    pub tracks: Vec<String>,
}

impl GrantScope {
    pub fn covers(&self, issue: &Issue) -> bool {
        if self.items.iter().any(|id| id == &issue.id) {
            return true;
        }
        match issue.track.as_deref() {
            Some(track) => self.tracks.iter().any(|candidate| candidate == track),
            None => false,
        }
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty() && self.tracks.is_empty()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Revocation {
    pub at: DateTime<Utc>,
    pub by: String,
    pub reason: String,
}

/// An explicit, authenticated grant of coordinator authority.
///
/// The grant binds a session label to that session's ownership proof (the
/// same SHA-256 token digest claims use). A label alone is never authority;
/// neither is a coord role, a pulse row, or a worker's secret.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Grant {
    pub id: String,
    pub coordinator_id: String,
    pub coordinator_proof: String,
    pub scope: GrantScope,
    pub reason: String,
    pub granted_at: DateTime<Utc>,
    pub granted_by: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revoked: Option<Revocation>,
}

impl Grant {
    pub fn is_live(&self) -> bool {
        self.revoked.is_none()
    }

    /// True when this session presents the exact proof the grant was issued
    /// to. Constant-time over the digest, like claim ownership.
    pub fn held_by(&self, session: &SessionIdentity) -> bool {
        self.coordinator_id == session.id() && constant_time_eq(&self.coordinator_proof, session.proof())
    }
}

fn constant_time_eq(left: &str, right: &str) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.as_bytes()
        .iter()
        .zip(right.as_bytes())
        .fold(0_u8, |difference, (left, right)| difference | (left ^ right))
        == 0
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GrantFile {
    #[serde(default = "one")]
    pub version: u32,
    #[serde(default)]
    pub grants: Vec<Grant>,
}

fn one() -> u32 {
    1
}

// ----------------------------------------------------------------------------
// Managed records
// ----------------------------------------------------------------------------

/// How an integration target reference resolved, so a reader never confuses
/// the checkout's HEAD with the branch the work actually landed on.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PinnedTarget {
    /// The reference as the caller spelled it.
    pub reference: String,
    /// The commit it resolved to when pinned.
    pub sha: String,
    /// `head`, `local_branch`, `remote_tracking`, `tag`, or `commit`.
    pub kind: String,
    pub pinned_at: DateTime<Utc>,
    pub pinned_by: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Correction {
    pub by: String,
    pub at: DateTime<Utc>,
    pub reason: String,
}

/// A worker's submission for one attempt. Submitting is not acceptance.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Submission {
    pub attempt: u32,
    pub by: String,
    pub at: DateTime<Utc>,
    /// The source revision the worker reports against, when it named one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revision: Option<String>,
    /// The report text, verbatim; the pointer-only drop carries its id.
    pub report: String,
    /// `submitted` or `correction_requested`.
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correction: Option<Correction>,
}

/// One required check, accepted by an authorized coordinator for one attempt
/// at one pinned integration target.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Acceptance {
    pub check: String,
    pub attempt: u32,
    pub target_sha: String,
    pub by: String,
    pub authority: String,
    pub at: DateTime<Utc>,
    pub evidence: String,
}

/// A coordinator releasing an attempt so a replacement may claim.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Release {
    pub attempt: u32,
    pub by: String,
    pub at: DateTime<Utc>,
    pub reason: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub worker: Option<String>,
    /// What coord reported for the worker at release time.
    pub worker_liveness: String,
    /// `coord_dead`, `worker_stopped` (attested), or `isolated_checkout`.
    pub basis: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub isolation: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ManagedRecord {
    pub id: String,
    /// Increments on every release; submissions and acceptances name the
    /// attempt they belong to, so a superseded worker cannot complete.
    pub attempt: u32,
    /// Check names that must each carry an acceptance before closure.
    pub required: Vec<String>,
    pub grant: String,
    pub managed_at: DateTime<Utc>,
    pub managed_by: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target: Option<PinnedTarget>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub submission: Option<Submission>,
    #[serde(default)]
    pub acceptances: Vec<Acceptance>,
    #[serde(default)]
    pub releases: Vec<Release>,
    /// Submissions superseded by a release, kept verbatim.
    #[serde(default)]
    pub history: Vec<Submission>,
}

impl ManagedRecord {
    pub fn accepted_checks(&self) -> Vec<&Acceptance> {
        let target = self.target.as_ref().map(|t| t.sha.as_str());
        self.acceptances
            .iter()
            .filter(|acceptance| acceptance.attempt == self.attempt)
            .filter(|acceptance| target == Some(acceptance.target_sha.as_str()))
            .collect()
    }

    pub fn outstanding_checks(&self) -> Vec<String> {
        let accepted = self.accepted_checks();
        self.required
            .iter()
            .filter(|check| !accepted.iter().any(|a| &a.check == *check))
            .cloned()
            .collect()
    }

    pub fn current_submission(&self) -> Option<&Submission> {
        self.submission
            .as_ref()
            .filter(|submission| submission.attempt == self.attempt)
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ManagedFile {
    #[serde(default = "one")]
    pub version: u32,
    #[serde(default)]
    pub items: BTreeMap<String, ManagedRecord>,
}

/// One append-only audit line.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LifecycleEvent {
    pub at: DateTime<Utc>,
    pub action: String,
    pub issue_id: String,
    pub actor: String,
    pub authority: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attempt: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<serde_json::Value>,
}

// ----------------------------------------------------------------------------
// Storage (caller holds the board lock for every write)
// ----------------------------------------------------------------------------

pub struct ManagedStore {
    manna_dir: PathBuf,
}

impl ManagedStore {
    pub fn new(base_dir: &Path) -> Self {
        ManagedStore {
            manna_dir: base_dir.join(".manna"),
        }
    }

    pub fn grants_path(&self) -> PathBuf {
        self.manna_dir.join(COORDINATORS_FILE)
    }

    pub fn managed_path(&self) -> PathBuf {
        self.manna_dir.join(MANAGED_FILE)
    }

    pub fn lifecycle_path(&self) -> PathBuf {
        self.manna_dir.join(LIFECYCLE_FILE)
    }

    fn reject_symlink(path: &Path) -> Result<(), String> {
        match fs::symlink_metadata(path) {
            Ok(metadata) if metadata.file_type().is_symlink() => Err(format!(
                "refusing symlinked Manna storage path {}",
                path.display()
            )),
            _ => Ok(()),
        }
    }

    fn read_json<T: Default + for<'de> Deserialize<'de>>(path: &Path) -> Result<T, String> {
        Self::reject_symlink(path)?;
        match fs::read_to_string(path) {
            Ok(text) if text.trim().is_empty() => Ok(T::default()),
            Ok(text) => serde_json::from_str(&text)
                .map_err(|error| format!("{} is not readable: {}", path.display(), error)),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(T::default()),
            Err(error) => Err(format!("failed to read {}: {}", path.display(), error)),
        }
    }

    fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
        Self::reject_symlink(path)?;
        let text = serde_json::to_string_pretty(value)
            .map_err(|error| format!("cannot serialize {}: {}", path.display(), error))?;
        let temp = path.with_extension(format!("json.{}.tmp", std::process::id()));
        {
            let mut file = OpenOptions::new()
                .create(true)
                .write(true)
                .truncate(true)
                .open(&temp)
                .map_err(|error| format!("cannot write {}: {}", temp.display(), error))?;
            file.write_all(text.as_bytes())
                .and_then(|_| file.write_all(b"\n"))
                .and_then(|_| file.sync_all())
                .map_err(|error| format!("cannot write {}: {}", temp.display(), error))?;
        }
        fs::rename(&temp, path).map_err(|error| {
            let _ = fs::remove_file(&temp);
            format!("cannot publish {}: {}", path.display(), error)
        })
    }

    pub fn load_grants(&self) -> Result<GrantFile, String> {
        Self::read_json(&self.grants_path())
    }

    pub fn save_grants(&self, grants: &GrantFile) -> Result<(), String> {
        Self::write_json(&self.grants_path(), grants)
    }

    pub fn load_managed(&self) -> Result<ManagedFile, String> {
        Self::read_json(&self.managed_path())
    }

    pub fn save_managed(&self, managed: &ManagedFile) -> Result<(), String> {
        Self::write_json(&self.managed_path(), managed)
    }

    pub fn record_for(&self, id: &str) -> Result<Option<ManagedRecord>, String> {
        Ok(self.load_managed()?.items.get(id).cloned())
    }

    pub fn append_event(&self, event: &LifecycleEvent) -> Result<(), String> {
        let path = self.lifecycle_path();
        Self::reject_symlink(&path)?;
        let line = serde_json::to_string(event)
            .map_err(|error| format!("cannot serialize lifecycle event: {}", error))?;
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
            .map_err(|error| format!("cannot open {}: {}", path.display(), error))?;
        file.write_all(line.as_bytes())
            .and_then(|_| file.write_all(b"\n"))
            .and_then(|_| file.sync_all())
            .map_err(|error| format!("cannot append {}: {}", path.display(), error))
    }

    pub fn events_for(&self, id: &str) -> Result<Vec<LifecycleEvent>, String> {
        let path = self.lifecycle_path();
        Self::reject_symlink(&path)?;
        let text = match fs::read_to_string(&path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => return Err(format!("failed to read {}: {}", path.display(), error)),
        };
        let mut events = Vec::new();
        for line in text.lines() {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<LifecycleEvent>(line) {
                Ok(event) if event.issue_id == id => events.push(event),
                Ok(_) => {}
                Err(error) => eprintln!("Warning: skipping malformed lifecycle line: {}", error),
            }
        }
        Ok(events)
    }

    /// Every managed sidecar that exists on this board, for tracking checks.
    pub fn present_files(&self) -> Vec<PathBuf> {
        [self.grants_path(), self.managed_path(), self.lifecycle_path()]
            .into_iter()
            .filter(|path| path.is_file())
            .collect()
    }
}

// ----------------------------------------------------------------------------
// Authority
// ----------------------------------------------------------------------------

/// What a session may do to a managed item, derived from explicit records
/// only. `operator` is the human at their own terminal (root); `coordinator`
/// is a live grant whose proof the session presents and whose scope covers
/// the item; `owner` is the claim-holder's proof; `none` is everyone else.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Authority {
    pub session: String,
    pub operator: bool,
    pub owner: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub grant: Option<String>,
    /// `operator`, `coordinator`, `owner`, or `none`: the strongest held.
    pub level: String,
}

impl Authority {
    pub fn resolve(session: &SessionIdentity, issue: &Issue, grants: &GrantFile) -> Authority {
        let operator = session.is_operator();
        let owner = issue.claimed_by.is_some() && !operator && issue.require_owner(session).is_ok();
        let grant = grants
            .grants
            .iter()
            .filter(|grant| grant.is_live())
            .filter(|grant| grant.held_by(session))
            .find(|grant| grant.scope.covers(issue))
            .map(|grant| grant.id.clone());
        let level = if operator {
            "operator"
        } else if grant.is_some() {
            "coordinator"
        } else if owner {
            "owner"
        } else {
            "none"
        };
        Authority {
            session: session.id().to_string(),
            operator,
            owner,
            grant,
            level: level.to_string(),
        }
    }

    pub fn coordinates(&self) -> bool {
        self.operator || self.grant.is_some()
    }
}

// ----------------------------------------------------------------------------
// Closure rule
// ----------------------------------------------------------------------------

/// Why a managed item cannot close right now. Empty means it can.
pub fn closure_blockers(issue: &Issue, record: &ManagedRecord) -> Vec<String> {
    let mut blockers = Vec::new();
    if issue.status == IssueStatus::Done {
        blockers.push(format!("{} is already done", issue.id));
        return blockers;
    }
    match record.current_submission() {
        None => blockers.push(format!(
            "no submission for attempt {} (worker runs `manna submit {} --report <file>`)",
            record.attempt, issue.id
        )),
        Some(submission) if submission.status == "correction_requested" => blockers.push(format!(
            "correction requested on attempt {}: {}",
            record.attempt,
            submission
                .correction
                .as_ref()
                .map(|c| c.reason.as_str())
                .unwrap_or("(no reason recorded)")
        )),
        Some(_) => {}
    }
    if record.target.is_none() {
        blockers.push(format!(
            "no integration target pinned (coordinator runs `manna accept {} --check <name> --target <ref> --evidence <text>`)",
            issue.id
        ));
    }
    for check in record.outstanding_checks() {
        blockers.push(format!(
            "required check `{}` has no acceptance for attempt {} at the pinned target",
            check, record.attempt
        ));
    }
    blockers
}

/// A digest of everything closure depends on. `done --assessment` carries it
/// back so a close refuses when any of it moved between look and act.
pub fn assessment_digest(issue: &Issue, record: Option<&ManagedRecord>) -> String {
    let mut hasher = Sha256::new();
    hasher.update(issue.id.as_bytes());
    hasher.update(b"|");
    hasher.update(issue.status.to_string().as_bytes());
    hasher.update(b"|");
    hasher.update(issue.claimed_by.as_deref().unwrap_or("").as_bytes());
    hasher.update(b"|");
    hasher.update(issue.updated_at.to_rfc3339().as_bytes());
    if let Some(record) = record {
        hasher.update(b"|attempt=");
        hasher.update(record.attempt.to_string().as_bytes());
        hasher.update(b"|target=");
        hasher.update(
            record
                .target
                .as_ref()
                .map(|t| t.sha.as_str())
                .unwrap_or("")
                .as_bytes(),
        );
        hasher.update(b"|submitted=");
        hasher.update(
            record
                .current_submission()
                .map(|s| s.at.to_rfc3339())
                .unwrap_or_default()
                .as_bytes(),
        );
        let mut accepted: Vec<String> = record
            .accepted_checks()
            .iter()
            .map(|a| format!("{}@{}", a.check, a.at.to_rfc3339()))
            .collect();
        accepted.sort();
        for entry in accepted {
            hasher.update(b"|accept=");
            hasher.update(entry.as_bytes());
        }
    }
    format!("assess:{:x}", hasher.finalize())
}

/// A stable, short grant id from its material.
pub fn grant_id(coordinator_id: &str, proof: &str, granted_at: &DateTime<Utc>) -> String {
    let mut hasher = Sha256::new();
    hasher.update(coordinator_id.as_bytes());
    hasher.update(b"|");
    hasher.update(proof.as_bytes());
    hasher.update(b"|");
    hasher.update(granted_at.to_rfc3339().as_bytes());
    let digest = format!("{:x}", hasher.finalize());
    format!("grant-{}", &digest[..12])
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn issue(id: &str) -> Issue {
        let mut issue = Issue::new(id.to_string(), "work".to_string()).unwrap();
        issue.track = Some("mn-track1".to_string());
        issue
    }

    fn identity(id: &str, token: &str) -> SessionIdentity {
        SessionIdentity::from_token(id, token).unwrap()
    }

    fn grant_for(session: &SessionIdentity, scope: GrantScope) -> Grant {
        Grant {
            id: "grant-x".to_string(),
            coordinator_id: session.id().to_string(),
            coordinator_proof: session.proof().to_string(),
            scope,
            reason: "test".to_string(),
            granted_at: Utc.with_ymd_and_hms(2026, 10, 30, 0, 0, 0).unwrap(),
            granted_by: "operator-erik".to_string(),
            revoked: None,
        }
    }

    #[test]
    fn a_label_without_the_proof_holds_no_grant() {
        let coordinator = identity("lead", "lead-token-00000000000000000000000000000000");
        let impostor = identity("lead", "other-token-0000000000000000000000000000000");
        let grants = GrantFile {
            version: 1,
            grants: vec![grant_for(
                &coordinator,
                GrantScope {
                    items: vec!["mn-aaa111".to_string()],
                    tracks: vec![],
                },
            )],
        };
        let target = issue("mn-aaa111");
        assert_eq!(
            Authority::resolve(&coordinator, &target, &grants).level,
            "coordinator"
        );
        assert_eq!(Authority::resolve(&impostor, &target, &grants).level, "none");
    }

    #[test]
    fn scope_is_items_or_tracks_and_nothing_else() {
        let coordinator = identity("lead", "lead-token-00000000000000000000000000000000");
        let grants = GrantFile {
            version: 1,
            grants: vec![grant_for(
                &coordinator,
                GrantScope {
                    items: vec![],
                    tracks: vec!["mn-track1".to_string()],
                },
            )],
        };
        let covered = issue("mn-aaa111");
        let mut outside = issue("mn-bbb222");
        outside.track = Some("mn-track2".to_string());
        assert_eq!(
            Authority::resolve(&coordinator, &covered, &grants).level,
            "coordinator"
        );
        assert_eq!(Authority::resolve(&coordinator, &outside, &grants).level, "none");
    }

    #[test]
    fn a_revoked_grant_is_no_grant() {
        let coordinator = identity("lead", "lead-token-00000000000000000000000000000000");
        let mut grant = grant_for(
            &coordinator,
            GrantScope {
                items: vec!["mn-aaa111".to_string()],
                tracks: vec![],
            },
        );
        grant.revoked = Some(Revocation {
            at: Utc::now(),
            by: "operator-erik".to_string(),
            reason: "done".to_string(),
        });
        let grants = GrantFile {
            version: 1,
            grants: vec![grant],
        };
        assert_eq!(
            Authority::resolve(&coordinator, &issue("mn-aaa111"), &grants).level,
            "none"
        );
    }

    fn record(attempt: u32) -> ManagedRecord {
        ManagedRecord {
            id: "mn-aaa111".to_string(),
            attempt,
            required: vec!["integration".to_string(), "deployed".to_string()],
            grant: "grant-x".to_string(),
            managed_at: Utc::now(),
            managed_by: "operator-erik".to_string(),
            target: None,
            submission: None,
            acceptances: Vec::new(),
            releases: Vec::new(),
            history: Vec::new(),
        }
    }

    #[test]
    fn closure_needs_submission_target_and_every_check() {
        let target = issue("mn-aaa111");
        let mut rec = record(1);
        let blockers = closure_blockers(&target, &rec);
        assert_eq!(blockers.len(), 4, "{blockers:?}");

        rec.submission = Some(Submission {
            attempt: 1,
            by: "worker".to_string(),
            at: Utc::now(),
            revision: None,
            report: "done".to_string(),
            status: "submitted".to_string(),
            correction: None,
        });
        rec.target = Some(PinnedTarget {
            reference: "origin/staging".to_string(),
            sha: "abc".to_string(),
            kind: "remote_tracking".to_string(),
            pinned_at: Utc::now(),
            pinned_by: "lead".to_string(),
        });
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 1,
            target_sha: "abc".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "merged".to_string(),
        });
        let blockers = closure_blockers(&target, &rec);
        assert_eq!(blockers.len(), 1, "{blockers:?}");
        assert!(blockers[0].contains("deployed"));

        rec.acceptances.push(Acceptance {
            check: "deployed".to_string(),
            attempt: 1,
            target_sha: "abc".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "release 42".to_string(),
        });
        assert!(closure_blockers(&target, &rec).is_empty());
    }

    #[test]
    fn acceptance_for_an_older_attempt_or_other_target_does_not_count() {
        let target = issue("mn-aaa111");
        let mut rec = record(2);
        rec.submission = Some(Submission {
            attempt: 2,
            by: "worker-2".to_string(),
            at: Utc::now(),
            revision: None,
            report: "redone".to_string(),
            status: "submitted".to_string(),
            correction: None,
        });
        rec.target = Some(PinnedTarget {
            reference: "main".to_string(),
            sha: "def".to_string(),
            kind: "local_branch".to_string(),
            pinned_at: Utc::now(),
            pinned_by: "lead".to_string(),
        });
        rec.required = vec!["integration".to_string()];
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 1,
            target_sha: "def".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "old attempt".to_string(),
        });
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 2,
            target_sha: "abc".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "other target".to_string(),
        });
        let blockers = closure_blockers(&target, &rec);
        assert_eq!(blockers.len(), 1, "{blockers:?}");
    }

    #[test]
    fn digest_moves_when_acceptance_state_moves() {
        let target = issue("mn-aaa111");
        let mut rec = record(1);
        let before = assessment_digest(&target, Some(&rec));
        rec.attempt = 2;
        let after = assessment_digest(&target, Some(&rec));
        assert_ne!(before, after);
        assert!(before.starts_with("assess:"));
    }
}
