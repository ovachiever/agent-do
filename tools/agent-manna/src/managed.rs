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
/// Transaction intents: a mutation's full outcome, written before the
/// sidecar and the audit line so a death or an unwritable destination
/// between the two leaves something recoverable, never a half-applied state
/// that looks whole.
pub const INTENT_FILE: &str = "managed-intent.json";
/// The issue id a board-level transaction (a coordinator grant or
/// revocation) carries. While one is incomplete, nothing managed moves and
/// no grant changes until `managed recover board` finishes it.
pub const BOARD_SCOPE: &str = "board";

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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrantFile {
    #[serde(default = "one")]
    pub version: u32,
    #[serde(default)]
    pub grants: Vec<Grant>,
}

/// The sidecar schema version every file on disk carries. A derived `Default`
/// wrote `0` for a fresh file while the read default was `1`, so a board whose
/// first `managed require` created `managed.json` carried a version no reader
/// of the contract (coord's assignment targeting) would accept (mn-54fe40).
pub const SIDECAR_VERSION: u32 = 1;

fn one() -> u32 {
    SIDECAR_VERSION
}

impl Default for GrantFile {
    fn default() -> Self {
        GrantFile { version: SIDECAR_VERSION, grants: Vec::new() }
    }
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
    /// Stable id for this exact submission (`sub-<12 hex>`). An acceptance
    /// names the id it reviewed; a resubmission mints a new one, so nothing
    /// accepted for the old result carries over.
    #[serde(default)]
    pub id: String,
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

/// One required check, accepted by an authorized coordinator for one exact
/// submission of one attempt at one pinned integration target.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Acceptance {
    pub check: String,
    pub attempt: u32,
    /// The submission key this verdict was given on. An acceptance written
    /// before this field existed carries none and never counts: a verdict
    /// that cannot name what it reviewed is not evidence for anything.
    #[serde(default)]
    pub submission: String,
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
    /// `coord_dead` (coord verified the worker dead or stopped),
    /// `isolated_checkout` (a validated separate working tree), or
    /// `abandon` (the worker released its own claim).
    pub basis: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub isolation: Option<String>,
    /// The replacement checkout's git toplevel as resolved at release time.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub isolation_toplevel: Option<String>,
    /// Two-phase marker: `pending` once the sidecar has advanced the attempt
    /// and before the board row's claim is released; `released` after. A
    /// `pending` entry whose worker still holds the claim is an interrupted
    /// release, and every mutation refuses until a coordinator resumes it.
    #[serde(default = "released")]
    pub claim_release: String,
}

fn released() -> String {
    "released".to_string()
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

impl Submission {
    /// The key an acceptance binds to. Submissions written before ids
    /// existed key on their attempt and timestamp, which no acceptance of
    /// that era recorded, so they too need a fresh verdict.
    pub fn key(&self) -> String {
        if self.id.is_empty() {
            format!("legacy:{}:{}", self.attempt, self.at.to_rfc3339())
        } else {
            self.id.clone()
        }
    }
}

impl ManagedRecord {
    /// Acceptances that count right now: same attempt, same pinned target,
    /// and given on the exact submission currently on the record.
    pub fn accepted_checks(&self) -> Vec<&Acceptance> {
        let target = self.target.as_ref().map(|t| t.sha.as_str());
        let Some(submission) = self.current_submission().map(Submission::key) else {
            return Vec::new();
        };
        self.acceptances
            .iter()
            .filter(|acceptance| acceptance.attempt == self.attempt)
            .filter(|acceptance| target == Some(acceptance.target_sha.as_str()))
            .filter(|acceptance| acceptance.submission == submission)
            .collect()
    }

    /// A release that advanced the attempt but never finished releasing the
    /// board row's claim (the process died between the two writes).
    pub fn pending_release(&self) -> Option<&Release> {
        self.releases
            .iter()
            .rev()
            .find(|release| release.claim_release == "pending")
    }

    /// True when a pending release is still interrupted: its worker still
    /// holds the claim on the row. A pending marker whose worker no longer
    /// holds the claim completed its row write and only lacks the marker.
    pub fn release_interrupted(&self, issue: &Issue) -> bool {
        match self.pending_release() {
            Some(release) => release.worker.is_some() && release.worker == issue.claimed_by,
            None => false,
        }
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManagedFile {
    #[serde(default = "one")]
    pub version: u32,
    #[serde(default)]
    pub items: BTreeMap<String, ManagedRecord>,
}

impl Default for ManagedFile {
    fn default() -> Self {
        ManagedFile { version: SIDECAR_VERSION, items: BTreeMap::new() }
    }
}

/// One append-only audit line.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LifecycleEvent {
    /// The transaction this line belongs to; recovery uses it to tell an
    /// audit line that landed from one that did not.
    #[serde(default)]
    pub txn: String,
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

/// A mutation's recorded outcome, durable before any of its writes. While
/// one is pending for an item, nothing else about that item may move.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Intent {
    pub txn: String,
    pub issue_id: String,
    pub action: String,
    pub started_at: DateTime<Utc>,
    pub actor: String,
    /// The actor's ownership proof, so the actor itself may recover.
    pub actor_proof: String,
    /// The managed record as it must read after this transaction, when the
    /// transaction writes one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub record_after: Option<ManagedRecord>,
    /// The grants file as it must read after this transaction, when the
    /// transaction writes it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub grants_after: Option<GrantFile>,
    /// The audit line this transaction must leave.
    pub event: LifecycleEvent,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntentFile {
    #[serde(default = "one")]
    pub version: u32,
    #[serde(default)]
    pub intents: Vec<Intent>,
}

impl Default for IntentFile {
    fn default() -> Self {
        IntentFile { version: SIDECAR_VERSION, intents: Vec::new() }
    }
}

/// A stable transaction id from its material.
pub fn transaction_id(issue_id: &str, action: &str, started_at: &DateTime<Utc>, actor: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(issue_id.as_bytes());
    hasher.update(b"|");
    hasher.update(action.as_bytes());
    hasher.update(b"|");
    hasher.update(started_at.to_rfc3339().as_bytes());
    hasher.update(b"|");
    hasher.update(actor.as_bytes());
    let digest = format!("{:x}", hasher.finalize());
    format!("txn-{}", &digest[..12])
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
        let mut grants: GrantFile = Self::read_json(&self.grants_path())?;
        if grants.version == 0 {
            // Written by a binary whose derived Default said 0; the next
            // save publishes the version the contract always meant.
            grants.version = SIDECAR_VERSION;
        }
        Ok(grants)
    }

    pub fn save_grants(&self, grants: &GrantFile) -> Result<(), String> {
        Self::write_json(&self.grants_path(), grants)
    }

    pub fn load_managed(&self) -> Result<ManagedFile, String> {
        let mut managed: ManagedFile = Self::read_json(&self.managed_path())?;
        if managed.version == 0 {
            managed.version = SIDECAR_VERSION;
        }
        Ok(managed)
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
        [self.grants_path(), self.managed_path(), self.lifecycle_path(), self.intents_path()]
            .into_iter()
            .filter(|path| path.is_file())
            .collect()
    }

    pub fn intents_path(&self) -> PathBuf {
        self.manna_dir.join(INTENT_FILE)
    }

    pub fn load_intents(&self) -> Result<IntentFile, String> {
        let mut intents: IntentFile = Self::read_json(&self.intents_path())?;
        if intents.version == 0 {
            intents.version = SIDECAR_VERSION;
        }
        Ok(intents)
    }

    pub fn save_intents(&self, intents: &IntentFile) -> Result<(), String> {
        if intents.intents.is_empty() {
            let path = self.intents_path();
            Self::reject_symlink(&path)?;
            return match fs::remove_file(&path) {
                Ok(()) => Ok(()),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                Err(error) => Err(format!("cannot remove {}: {}", path.display(), error)),
            };
        }
        Self::write_json(&self.intents_path(), intents)
    }

    /// Pending transactions for one item.
    pub fn pending_intents_for(&self, id: &str) -> Result<Vec<Intent>, String> {
        Ok(self
            .load_intents()?
            .intents
            .into_iter()
            .filter(|intent| intent.issue_id == id)
            .collect())
    }

    /// Pending transactions that hold an item still: its own, and any
    /// board-level one (a grant or revocation whose writes did not both land
    /// leaves every coordinator's authority in doubt).
    pub fn pending_intents_affecting(&self, id: &str) -> Result<Vec<Intent>, String> {
        Ok(self
            .load_intents()?
            .intents
            .into_iter()
            .filter(|intent| intent.issue_id == id || intent.issue_id == BOARD_SCOPE)
            .collect())
    }

    /// The refusal every mutation gives while a transaction on the item, or
    /// on the board, is incomplete; `None` when nothing is pending. Asked
    /// with `BOARD_SCOPE`, it answers for the board alone.
    pub fn incomplete_transaction(&self, id: &str) -> Result<Option<String>, String> {
        let intents = self.load_intents()?.intents;
        if id != BOARD_SCOPE {
            if let Some(intent) = intents.iter().find(|intent| intent.issue_id == id) {
                return Ok(Some(format!(
                    "{} has an incomplete transaction {} ({} by {} at {}): its state and audit writes did not both land; run `manna managed recover {}` before anything else moves",
                    id,
                    intent.txn,
                    intent.action,
                    intent.actor,
                    intent.started_at.to_rfc3339(),
                    id
                )));
            }
        }
        Ok(intents
            .iter()
            .find(|intent| intent.issue_id == BOARD_SCOPE)
            .map(|intent| {
                format!(
                    "the board has an incomplete coordinator transaction {} ({} by {} at {}): its grants and audit writes did not both land; the operator runs `manna managed recover board` before anything managed moves",
                    intent.txn,
                    intent.action,
                    intent.actor,
                    intent.started_at.to_rfc3339()
                )
            }))
    }

    /// Run one mutation as a recoverable transaction, under the caller's
    /// board lock: the intent (the complete outcome) is durable first, then
    /// the state writes, then the audit line, then the intent is retired.
    /// A failure after the intent is durable leaves it pending; the item
    /// refuses every other mutation until `recover` finishes the job.
    pub fn run_transaction(&self, intent: Intent) -> Result<(), String> {
        self.begin_transaction(&intent)?;
        self.finish_transaction(&intent)
    }

    /// Make the intent durable: from here the outcome is recoverable.
    pub fn begin_transaction(&self, intent: &Intent) -> Result<(), String> {
        let mut intents = self.load_intents()?;
        intents.intents.push(intent.clone());
        self.save_intents(&intents)
    }

    /// The writes the intent names, then its retirement.
    pub fn finish_transaction(&self, intent: &Intent) -> Result<(), String> {
        self.apply_intent(intent)?;
        self.retire_intent(&intent.txn)
    }

    /// Apply an intent's writes idempotently: the state files take the
    /// recorded "after" images; the audit line is appended unless a line
    /// with this transaction id already exists.
    pub fn apply_intent(&self, intent: &Intent) -> Result<(), String> {
        if let Some(record) = intent.record_after.as_ref() {
            let mut managed = self.load_managed()?;
            managed.items.insert(record.id.clone(), record.clone());
            self.save_managed(&managed)?;
        }
        if let Some(grants) = intent.grants_after.as_ref() {
            self.save_grants(grants)?;
        }
        if !self.event_landed(&intent.txn)? {
            self.append_event(&intent.event)?;
        }
        Ok(())
    }

    pub fn retire_intent(&self, txn: &str) -> Result<(), String> {
        let mut intents = self.load_intents()?;
        intents.intents.retain(|intent| intent.txn != txn);
        self.save_intents(&intents)
    }

    /// True when the audit already holds a line for this transaction.
    pub fn event_landed(&self, txn: &str) -> Result<bool, String> {
        let path = self.lifecycle_path();
        Self::reject_symlink(&path)?;
        let text = match fs::read_to_string(&path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => return Err(format!("failed to read {}: {}", path.display(), error)),
        };
        Ok(text.lines().any(|line| {
            serde_json::from_str::<LifecycleEvent>(line)
                .map(|event| event.txn == txn)
                .unwrap_or(false)
        }))
    }

    /// Finish every pending transaction for an item. Returns the retired
    /// transaction ids.
    pub fn recover(&self, id: &str) -> Result<Vec<String>, String> {
        let pending = self.pending_intents_for(id)?;
        self.recover_intents(&pending)
    }

    /// Finish exactly these transactions, in order, and nothing else: the
    /// caller read and authorized this list under the board lock, so a
    /// transaction that is no longer pending (or never was) is refused
    /// rather than replayed from the caller's copy. Returns the retired
    /// transaction ids.
    pub fn recover_intents(&self, intents: &[Intent]) -> Result<Vec<String>, String> {
        let pending = self.load_intents()?.intents;
        let mut recovered = Vec::new();
        for intent in intents {
            let current = pending
                .iter()
                .find(|candidate| candidate.txn == intent.txn)
                .ok_or_else(|| {
                    format!(
                        "transaction {} is not pending; recovery replays only the transactions it authorized under the lock",
                        intent.txn
                    )
                })?;
            self.apply_intent(current)?;
            self.retire_intent(&current.txn)?;
            recovered.push(current.txn.clone());
        }
        Ok(recovered)
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
    if record.release_interrupted(issue) {
        blockers.push(format!(
            "a release of attempt {} was interrupted before the claim came off the row; a coordinator runs `manna managed release {} --reason <text>` to complete it",
            record.attempt.saturating_sub(1),
            issue.id
        ));
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

/// The conditions an assessment was computed under. The token carries them
/// so a close can recompute the same conditions under the lock: a blocked
/// assessment never authorizes a close, and a closable one authorizes only
/// while the integration reference, the requested target, and every input
/// to the verdict still read the same.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AssessmentConditions {
    pub closable: bool,
    pub blockers: Vec<String>,
    /// The sha the caller's `--target` resolved to, when one was given.
    pub requested_sha: Option<String>,
    /// Where the pinned reference name points now, when a target is pinned.
    pub pinned_reference_now: Option<String>,
}

/// Build the assessment token. `assess:v2:<requested|->:<pinned-now|->:<hex>`
/// for a closable verdict, `blocked:v2:<hex>` otherwise. The hex covers the
/// board row, the managed record's acceptance state, and the conditions.
pub fn assessment_token(issue: &Issue, record: Option<&ManagedRecord>, conditions: &AssessmentConditions) -> String {
    let requested = conditions.requested_sha.clone().unwrap_or_else(|| "-".to_string());
    let pinned_now = conditions.pinned_reference_now.clone().unwrap_or_else(|| "-".to_string());
    let hex = assessment_hex(issue, record, conditions, &requested, &pinned_now);
    if conditions.closable {
        format!("assess:v2:{}:{}:{}", requested, pinned_now, hex)
    } else {
        format!("blocked:v2:{}", hex)
    }
}

/// A parsed closable token: the conditions it was computed under.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClosableToken {
    pub requested_sha: Option<String>,
    pub pinned_reference_now: Option<String>,
    pub hex: String,
}

/// Parse a token handed back to `done`. `Err` names why it can never
/// authorize a close (blocked, old format, garbage).
pub fn parse_assessment_token(token: &str) -> Result<ClosableToken, String> {
    if let Some(rest) = token.strip_prefix("blocked:v2:") {
        let _ = rest;
        return Err("the assessment handed in was blocked; a blocked assessment never authorizes a close. Resolve its blockers and re-run `manna assess`".to_string());
    }
    let Some(rest) = token.strip_prefix("assess:v2:") else {
        return Err(format!(
            "unrecognized assessment token `{}`; re-run `manna assess` and hand in the current one",
            token
        ));
    };
    let parts: Vec<&str> = rest.splitn(3, ':').collect();
    if parts.len() != 3 || parts[2].len() != 64 {
        return Err(format!("malformed assessment token `{}`; re-run `manna assess`", token));
    }
    let optional = |value: &str| (value != "-").then(|| value.to_string());
    Ok(ClosableToken {
        requested_sha: optional(parts[0]),
        pinned_reference_now: optional(parts[1]),
        hex: parts[2].to_string(),
    })
}

/// Recompute the hex for a closable verdict under the same inputs the token
/// names; equality means nothing the verdict depended on moved.
pub fn closable_hex(issue: &Issue, record: Option<&ManagedRecord>, token: &ClosableToken) -> String {
    let conditions = AssessmentConditions {
        closable: true,
        blockers: Vec::new(),
        requested_sha: token.requested_sha.clone(),
        pinned_reference_now: token.pinned_reference_now.clone(),
    };
    let requested = token.requested_sha.clone().unwrap_or_else(|| "-".to_string());
    let pinned_now = token.pinned_reference_now.clone().unwrap_or_else(|| "-".to_string());
    assessment_hex(issue, record, &conditions, &requested, &pinned_now)
}

fn assessment_hex(
    issue: &Issue,
    record: Option<&ManagedRecord>,
    conditions: &AssessmentConditions,
    requested: &str,
    pinned_now: &str,
) -> String {
    let mut hasher = Sha256::new();
    hasher.update(assessment_digest(issue, record).as_bytes());
    hasher.update(b"|closable=");
    hasher.update(if conditions.closable { b"1" } else { b"0" });
    let mut blockers = conditions.blockers.clone();
    blockers.sort();
    for blocker in blockers {
        hasher.update(b"|blocker=");
        hasher.update(blocker.as_bytes());
    }
    hasher.update(b"|requested=");
    hasher.update(requested.as_bytes());
    hasher.update(b"|pinned_now=");
    hasher.update(pinned_now.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// A digest of the board row and the managed record's acceptance state.
/// The assessment token builds on it; it is not itself an authorization.
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
                .map(|s| format!("{}@{}:{}", s.key(), s.at.to_rfc3339(), s.status))
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

/// A stable, short submission id from its material.
pub fn submission_id(attempt: u32, by: &str, at: &DateTime<Utc>, report: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(attempt.to_string().as_bytes());
    hasher.update(b"|");
    hasher.update(by.as_bytes());
    hasher.update(b"|");
    hasher.update(at.to_rfc3339().as_bytes());
    hasher.update(b"|");
    hasher.update(report.as_bytes());
    let digest = format!("{:x}", hasher.finalize());
    format!("sub-{}", &digest[..12])
}

/// Authority re-derived inside a locked mutation: the grant must still be
/// live, still held by this session's proof, and still cover the row as it
/// is now. The operator needs no grant. Returns the level or a refusal.
pub fn revalidate_authority(
    session: &SessionIdentity,
    issue: &Issue,
    grants: &GrantFile,
    verb: &str,
) -> Result<Authority, String> {
    let authority = Authority::resolve(session, issue, grants);
    if authority.coordinates() {
        Ok(authority)
    } else {
        Err(format!(
            "{} refused under the lock: this session no longer holds coordinator authority over {} (level now: {}); a revoked grant or a changed scope does not carry an earlier look forward",
            verb, issue.id, authority.level
        ))
    }
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
            id: "sub-aaaaaaaaaaaa".to_string(),
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
            submission: "sub-aaaaaaaaaaaa".to_string(),
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
            submission: "sub-aaaaaaaaaaaa".to_string(),
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
            id: "sub-bbbbbbbbbbbb".to_string(),
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
            submission: "sub-bbbbbbbbbbbb".to_string(),
            target_sha: "def".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "old attempt".to_string(),
        });
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 2,
            submission: "sub-bbbbbbbbbbbb".to_string(),
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
    fn acceptance_binds_to_the_exact_submission() {
        let target = issue("mn-aaa111");
        let mut rec = record(1);
        rec.required = vec!["integration".to_string()];
        rec.target = Some(PinnedTarget {
            reference: "main".to_string(),
            sha: "abc".to_string(),
            kind: "local_branch".to_string(),
            pinned_at: Utc::now(),
            pinned_by: "lead".to_string(),
        });
        let first = Submission {
            id: "sub-aaaaaaaaaaaa".to_string(),
            attempt: 1,
            by: "worker".to_string(),
            at: Utc::now(),
            revision: None,
            report: "A".to_string(),
            status: "submitted".to_string(),
            correction: None,
        };
        rec.submission = Some(first.clone());
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 1,
            submission: first.key(),
            target_sha: "abc".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "reviewed A".to_string(),
        });
        assert!(closure_blockers(&target, &rec).is_empty(), "A is accepted");

        // Correction requested, then a changed submission B on the same attempt.
        let mut corrected = first.clone();
        corrected.status = "correction_requested".to_string();
        rec.submission = Some(corrected);
        assert!(!closure_blockers(&target, &rec).is_empty(), "a correction blocks");
        rec.history.push(rec.submission.take().unwrap());
        rec.submission = Some(Submission {
            id: "sub-bbbbbbbbbbbb".to_string(),
            attempt: 1,
            by: "worker".to_string(),
            at: Utc::now(),
            revision: None,
            report: "B".to_string(),
            status: "submitted".to_string(),
            correction: None,
        });
        let blockers = closure_blockers(&target, &rec);
        assert_eq!(blockers.len(), 1, "{blockers:?}");
        assert!(blockers[0].contains("integration"), "A's verdict must not carry to B");
    }

    #[test]
    fn an_acceptance_that_names_no_submission_never_counts() {
        let target = issue("mn-aaa111");
        let mut rec = record(1);
        rec.required = vec!["integration".to_string()];
        rec.target = Some(PinnedTarget {
            reference: "main".to_string(),
            sha: "abc".to_string(),
            kind: "local_branch".to_string(),
            pinned_at: Utc::now(),
            pinned_by: "lead".to_string(),
        });
        rec.submission = Some(Submission {
            id: String::new(),
            attempt: 1,
            by: "worker".to_string(),
            at: Utc::now(),
            revision: None,
            report: "old".to_string(),
            status: "submitted".to_string(),
            correction: None,
        });
        rec.acceptances.push(Acceptance {
            check: "integration".to_string(),
            attempt: 1,
            submission: String::new(),
            target_sha: "abc".to_string(),
            by: "lead".to_string(),
            authority: "coordinator".to_string(),
            at: Utc::now(),
            evidence: "pre-binding record".to_string(),
        });
        assert_eq!(closure_blockers(&target, &rec).len(), 1);
    }

    #[test]
    fn an_interrupted_release_blocks_until_resumed() {
        let mut target = issue("mn-aaa111");
        target.claimed_by = Some("worker".to_string());
        let mut rec = record(2);
        rec.releases.push(Release {
            attempt: 1,
            by: "lead".to_string(),
            at: Utc::now(),
            reason: "gone".to_string(),
            worker: Some("worker".to_string()),
            worker_liveness: "dead".to_string(),
            basis: "coord_dead".to_string(),
            isolation: None,
            isolation_toplevel: None,
            claim_release: "pending".to_string(),
        });
        assert!(rec.release_interrupted(&target));
        assert!(closure_blockers(&target, &rec)
            .iter()
            .any(|b| b.contains("interrupted")));
        target.claimed_by = None;
        assert!(!rec.release_interrupted(&target), "row released: only the marker is missing");
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

    #[test]
    fn a_blocked_assessment_token_never_parses_as_closable() {
        let target = issue("mn-aaa111");
        let rec = record(1);
        let blocked = assessment_token(
            &target,
            Some(&rec),
            &AssessmentConditions {
                closable: false,
                blockers: vec!["requested target moved".to_string()],
                requested_sha: Some("bc6361".to_string()),
                pinned_reference_now: Some("bc6361".to_string()),
            },
        );
        assert!(blocked.starts_with("blocked:v2:"));
        let error = parse_assessment_token(&blocked).unwrap_err();
        assert!(error.contains("blocked"), "{error}");
        assert!(parse_assessment_token("assess:deadbeef").is_err(), "v1 tokens are refused");
        assert!(parse_assessment_token("garbage").is_err());
    }

    #[test]
    fn a_closable_token_binds_its_conditions() {
        let target = issue("mn-aaa111");
        let rec = record(1);
        let conditions = AssessmentConditions {
            closable: true,
            blockers: Vec::new(),
            requested_sha: Some("4d5519".to_string()),
            pinned_reference_now: Some("4d5519".to_string()),
        };
        let token = assessment_token(&target, Some(&rec), &conditions);
        let parsed = parse_assessment_token(&token).unwrap();
        assert_eq!(parsed.requested_sha.as_deref(), Some("4d5519"));
        assert_eq!(parsed.pinned_reference_now.as_deref(), Some("4d5519"));
        assert_eq!(closable_hex(&target, Some(&rec), &parsed), parsed.hex);
        // The reference moved: the same token no longer reproduces.
        let moved = ClosableToken {
            pinned_reference_now: Some("bc6361".to_string()),
            ..parsed.clone()
        };
        assert_ne!(closable_hex(&target, Some(&rec), &moved), parsed.hex);
    }
    #[test]
    fn a_fresh_sidecar_carries_version_one_and_a_zero_on_disk_reads_as_one() {
        // mn-54fe40: the derived Default wrote `"version": 0` for the first
        // `managed require` on a board, and coord's assignment targeting
        // refused every item-addressed drop on it ("invalid managed metadata").
        assert_eq!(ManagedFile::default().version, SIDECAR_VERSION);
        assert_eq!(GrantFile::default().version, SIDECAR_VERSION);
        assert_eq!(IntentFile::default().version, SIDECAR_VERSION);
        let temp = tempfile::tempdir().unwrap();
        let store = store_in(temp.path());
        store.save_managed(&ManagedFile::default()).unwrap();
        let written: serde_json::Value = serde_json::from_str(&fs::read_to_string(store.managed_path()).unwrap()).unwrap();
        assert_eq!(written["version"], serde_json::json!(SIDECAR_VERSION));
        fs::write(store.managed_path(), "{\"version\": 0, \"items\": {}}\n").unwrap();
        assert_eq!(store.load_managed().unwrap().version, SIDECAR_VERSION);
        fs::write(store.grants_path(), "{\"version\": 0, \"grants\": []}\n").unwrap();
        assert_eq!(store.load_grants().unwrap().version, SIDECAR_VERSION);
        fs::write(store.intents_path(), "{\"version\": 0, \"intents\": []}\n").unwrap();
        assert_eq!(store.load_intents().unwrap().version, SIDECAR_VERSION);
    }

    fn store_in(dir: &Path) -> ManagedStore {
        fs::create_dir_all(dir.join(".manna")).unwrap();
        ManagedStore::new(dir)
    }

    fn board_intent(action: &str, grants_after: GrantFile) -> Intent {
        let started_at = Utc.with_ymd_and_hms(2026, 10, 30, 22, 29, 42).unwrap();
        let txn = transaction_id(BOARD_SCOPE, action, &started_at, "operator-erik");
        Intent {
            txn: txn.clone(),
            issue_id: BOARD_SCOPE.to_string(),
            action: action.to_string(),
            started_at,
            actor: "operator-erik".to_string(),
            actor_proof: "sha256:operator".to_string(),
            record_after: None,
            grants_after: Some(grants_after),
            event: LifecycleEvent {
                txn,
                at: started_at,
                action: action.to_string(),
                issue_id: BOARD_SCOPE.to_string(),
                actor: "operator-erik".to_string(),
                authority: "operator".to_string(),
                attempt: None,
                reason: Some("fixture".to_string()),
                evidence: None,
                detail: None,
            },
        }
    }

    #[test]
    fn a_pending_board_transaction_holds_every_item_and_names_board_recovery() {
        let dir = tempfile::TempDir::new().unwrap();
        let store = store_in(dir.path());
        let lead = identity("lead", "lead-token-0123456789abcdefghijklmnop");
        let grants = GrantFile {
            version: 1,
            grants: vec![grant_for(&lead, GrantScope { items: vec!["mn-x".to_string()], tracks: vec![] })],
        };
        assert_eq!(store.incomplete_transaction("mn-x").unwrap(), None);
        store.begin_transaction(&board_intent("grant", grants)).unwrap();
        // Nothing wrote the grants or the audit: the board alone is pending.
        let refusal = store.incomplete_transaction("mn-x").unwrap().expect("an item refuses");
        assert!(refusal.contains("board has an incomplete coordinator transaction"), "{}", refusal);
        assert!(refusal.contains("manna managed recover board"), "{}", refusal);
        let board = store.incomplete_transaction(BOARD_SCOPE).unwrap().expect("the board refuses");
        assert!(board.contains("recover board"), "{}", board);
        // The item's own pending set is empty; the affecting set holds the board's.
        assert!(store.pending_intents_for("mn-x").unwrap().is_empty());
        assert_eq!(store.pending_intents_affecting("mn-x").unwrap().len(), 1);
        assert_eq!(store.pending_intents_affecting("mn-x").unwrap()[0].issue_id, BOARD_SCOPE);
    }

    #[test]
    fn recovering_the_board_lands_the_grants_and_the_audit_exactly_once() {
        let dir = tempfile::TempDir::new().unwrap();
        let store = store_in(dir.path());
        let lead = identity("lead", "lead-token-0123456789abcdefghijklmnop");
        let grants = GrantFile {
            version: 1,
            grants: vec![grant_for(&lead, GrantScope { items: vec!["mn-x".to_string()], tracks: vec![] })],
        };
        let intent = board_intent("grant", grants);
        store.begin_transaction(&intent).unwrap();
        assert!(store.load_grants().unwrap().grants.is_empty(), "the grant did not land before recovery");
        let recovered = store.recover(BOARD_SCOPE).unwrap();
        assert_eq!(recovered, vec![intent.txn.clone()]);
        assert_eq!(store.load_grants().unwrap().grants.len(), 1, "recovery wrote the recorded grants");
        assert_eq!(store.events_for(BOARD_SCOPE).unwrap().len(), 1, "recovery wrote the audit line");
        assert!(store.event_landed(&intent.txn).unwrap());
        assert_eq!(store.incomplete_transaction("mn-x").unwrap(), None, "the item moves again");
        assert!(!store.intents_path().exists(), "no intent remains");
        // Recovering again is a no-op: nothing doubles.
        assert!(store.recover(BOARD_SCOPE).unwrap().is_empty());
        assert_eq!(store.events_for(BOARD_SCOPE).unwrap().len(), 1);
        assert_eq!(store.load_grants().unwrap().grants.len(), 1);
    }

    #[test]
    fn a_pending_revocation_whose_state_did_not_land_is_still_a_pending_revocation() {
        // The grants file still shows the grant live; the intent says it is
        // revoked. Until recovery, the file is not the truth: everything
        // managed refuses, and recovery writes the revocation.
        let dir = tempfile::TempDir::new().unwrap();
        let store = store_in(dir.path());
        let lead = identity("lead", "lead-token-0123456789abcdefghijklmnop");
        let live = grant_for(&lead, GrantScope { items: vec!["mn-x".to_string()], tracks: vec![] });
        store.save_grants(&GrantFile { version: 1, grants: vec![live.clone()] }).unwrap();
        let mut revoked = live.clone();
        revoked.revoked = Some(Revocation {
            at: Utc.with_ymd_and_hms(2026, 10, 30, 22, 30, 0).unwrap(),
            by: "operator-erik".to_string(),
            reason: "rotate".to_string(),
        });
        let intent = board_intent("revoke", GrantFile { version: 1, grants: vec![revoked] });
        store.begin_transaction(&intent).unwrap();
        assert!(store.load_grants().unwrap().grants[0].is_live(), "the file still says live");
        assert!(store.incomplete_transaction("mn-x").unwrap().is_some(), "but nothing moves");
        store.recover(BOARD_SCOPE).unwrap();
        assert!(!store.load_grants().unwrap().grants[0].is_live(), "recovery lands the revocation");
        assert_eq!(store.events_for(BOARD_SCOPE).unwrap().len(), 1);
    }

    fn item_intent(action: &str, second: u32) -> Intent {
        let started_at = Utc.with_ymd_and_hms(2026, 10, 31, 0, 30, second).unwrap();
        let txn = transaction_id("mn-aaa111", action, &started_at, "review-worker");
        Intent {
            txn: txn.clone(),
            issue_id: "mn-aaa111".to_string(),
            action: action.to_string(),
            started_at,
            actor: "review-worker".to_string(),
            actor_proof: "sha256:worker".to_string(),
            record_after: Some(record(1)),
            grants_after: None,
            event: LifecycleEvent {
                txn,
                at: started_at,
                action: action.to_string(),
                issue_id: "mn-aaa111".to_string(),
                actor: "review-worker".to_string(),
                authority: "owner".to_string(),
                attempt: Some(1),
                reason: None,
                evidence: None,
                detail: None,
            },
        }
    }

    #[test]
    fn recovery_replays_only_the_transactions_it_authorized() {
        // The caller authorizes a list it read under the lock; recovery
        // finishes that list and nothing else, and a copy of a transaction
        // that is no longer pending is refused rather than replayed.
        let dir = tempfile::TempDir::new().unwrap();
        let store = store_in(dir.path());
        let first = item_intent("submit", 9);
        let second = item_intent("accept", 10);
        store.begin_transaction(&first).unwrap();
        store.begin_transaction(&second).unwrap();
        let recovered = store.recover_intents(std::slice::from_ref(&first)).unwrap();
        assert_eq!(recovered, vec![first.txn.clone()]);
        assert!(store.event_landed(&first.txn).unwrap());
        assert!(!store.event_landed(&second.txn).unwrap(), "the transaction nobody authorized was not replayed");
        assert_eq!(store.pending_intents_for("mn-aaa111").unwrap().len(), 1);
        let refused = store.recover_intents(std::slice::from_ref(&first)).unwrap_err();
        assert!(refused.contains("is not pending"), "{}", refused);
        assert_eq!(store.events_for("mn-aaa111").unwrap().len(), 1, "nothing doubled");
        assert_eq!(store.recover("mn-aaa111").unwrap(), vec![second.txn.clone()]);
        assert!(!store.intents_path().exists(), "no intent remains");
    }
}
