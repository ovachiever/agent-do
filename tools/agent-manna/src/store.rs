//! JSONL storage with file locking for Manna.
//!
//! Storage files:
//! - `.manna/issues.jsonl` - Issue records
//! - `.manna/sessions.jsonl` - Session event log

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use fs2::FileExt;
use rand::{rngs::OsRng, RngCore};

use crate::error::{MannaError, Result};
use crate::issue::{Issue, IssueStatus, SessionEvent, SessionIdentity};

/// Directory name for Manna storage.
const MANNA_DIR: &str = ".manna";

/// Issues JSONL file name.
const ISSUES_FILE: &str = "issues.jsonl";

/// Sessions JSONL file name.
const SESSIONS_FILE: &str = "sessions.jsonl";

/// Board-wide mutation lock file name.
const BOARD_LOCK_FILE: &str = "board.lock";
const BOARD_IDENTITY_FILE: &str = "board.yaml";

/// Manna storage backed by JSONL files.
///
/// All writes acquire exclusive file locks to prevent corruption
/// during concurrent access.
#[derive(Debug, Clone)]
pub struct MannaStore {
    /// Base directory containing `.manna/`.
    base_dir: PathBuf,
}

/// The completed row and dependents that became unblocked in the same write.
pub struct CompletedIssue {
    pub issue: Issue,
    pub released: Vec<String>,
}

impl MannaStore {
    /// Create a new MannaStore rooted at the given directory.
    ///
    /// Does not initialize storage; call `init()` first.
    pub fn new<P: AsRef<Path>>(base_dir: P) -> Self {
        MannaStore {
            base_dir: base_dir.as_ref().to_path_buf(),
        }
    }

    /// Get the `.manna` directory path.
    fn manna_dir(&self) -> PathBuf {
        self.base_dir.join(MANNA_DIR)
    }

    /// Get the issues.jsonl file path.
    fn issues_path(&self) -> PathBuf {
        self.manna_dir().join(ISSUES_FILE)
    }

    /// Get the sessions.jsonl file path.
    fn sessions_path(&self) -> PathBuf {
        self.manna_dir().join(SESSIONS_FILE)
    }

    fn board_lock_path(&self) -> PathBuf {
        self.manna_dir().join(BOARD_LOCK_FILE)
    }

    fn board_is_strict(&self) -> Result<bool> {
        let path = self.manna_dir().join(BOARD_IDENTITY_FILE);
        if !path.exists() {
            return Ok(false);
        }
        let text = fs::read_to_string(&path)?;
        let identity: serde_yaml::Value = serde_yaml::from_str(&text).map_err(|error| {
            MannaError::MutationRejected(format!(
                "invalid board identity {}: {}",
                path.display(),
                error
            ))
        })?;
        match identity.get("workflow").and_then(serde_yaml::Value::as_str) {
            Some("strict") => Ok(true),
            Some("legacy") => Ok(false),
            Some(mode) => Err(MannaError::MutationRejected(format!(
                "unsupported board workflow mode {}",
                mode
            ))),
            None => Err(MannaError::MutationRejected(
                "board identity has no workflow mode".to_string(),
            )),
        }
    }

    fn validate_strict_row_shapes(issues: &[Issue]) -> Result<()> {
        for issue in issues
            .iter()
            .filter(|issue| issue.status != crate::issue::IssueStatus::Done)
        {
            match issue.issue_type {
                crate::issue::IssueType::Item
                    if issue.prompt.is_none() || issue.handoff_digest.is_none() =>
                {
                    return Err(MannaError::MutationRejected(format!(
                        "strict workflow item {} is missing its authoritative handoff pair",
                        issue.id
                    )));
                }
                crate::issue::IssueType::Track | crate::issue::IssueType::Dream
                    if issue.prompt.is_some() || issue.handoff_digest.is_some() =>
                {
                    return Err(MannaError::MutationRejected(format!(
                        "strict workflow {} {} cannot carry an item handoff",
                        issue.issue_type, issue.id
                    )));
                }
                _ => {}
            }
        }
        Ok(())
    }

    /// Refuse storage whose root or durable files are symlinks. Checking only
    /// the leaf after opening it is too late: a symlinked `.manna/` redirects
    /// every board mutation outside the project.
    pub fn validate_storage_root(&self) -> Result<()> {
        for path in [
            self.manna_dir(),
            self.issues_path(),
            self.sessions_path(),
            self.board_lock_path(),
            self.manna_dir().join(BOARD_IDENTITY_FILE),
        ] {
            match fs::symlink_metadata(&path) {
                Ok(metadata) if metadata.file_type().is_symlink() => {
                    return Err(MannaError::MutationRejected(format!(
                        "refusing symlinked Manna storage path {}",
                        path.display()
                    )))
                }
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error.into()),
            }
        }
        Ok(())
    }

    /// Initialize storage by creating `.manna/` directory and JSONL files.
    ///
    /// This is idempotent - running twice does not error.
    pub fn init(&self) -> Result<()> {
        self.validate_storage_root()?;
        let manna_dir = self.manna_dir();

        // Create .manna directory if it doesn't exist
        if !manna_dir.exists() {
            fs::create_dir_all(&manna_dir)?;
        }

        // Create issues.jsonl if it doesn't exist
        let issues_path = self.issues_path();
        if !issues_path.exists() {
            File::create(&issues_path)?;
        }

        // Create sessions.jsonl if it doesn't exist
        let sessions_path = self.sessions_path();
        if !sessions_path.exists() {
            File::create(&sessions_path)?;
        }

        Ok(())
    }

    /// Check if storage is initialized.
    pub fn is_initialized(&self) -> bool {
        self.validate_storage_root().is_ok()
            && self.manna_dir().exists()
            && self.issues_path().exists()
            && self.sessions_path().exists()
    }

    /// Load all issues from issues.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_issues(&self) -> Result<Vec<Issue>> {
        self.load_issues_internal(true)
    }

    /// Load the complete board without dropping an unreadable record.
    /// Whole-board transactions use this path because rewriting after a
    /// skipped line would silently convert corruption into data loss.
    pub fn load_issues_strict(&self) -> Result<Vec<Issue>> {
        self.load_issues_internal(false)
    }

    fn load_issues_internal(&self, skip_malformed: bool) -> Result<Vec<Issue>> {
        self.validate_storage_root()?;
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = File::open(&path)?;
        let reader = BufReader::new(file);
        let mut issues = Vec::new();

        for (line_num, line_result) in reader.lines().enumerate() {
            let line = match line_result {
                Ok(l) => l,
                Err(e) => {
                    if !skip_malformed {
                        return Err(MannaError::MutationRejected(format!(
                            "cannot read complete board line {} in {}: {}",
                            line_num + 1,
                            path.display(),
                            e
                        )));
                    }
                    eprintln!(
                        "Warning: Failed to read line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                    continue;
                }
            };

            // Skip empty lines
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<Issue>(&line) {
                Ok(issue) => issues.push(issue),
                Err(e) => {
                    if !skip_malformed {
                        return Err(MannaError::MutationRejected(format!(
                            "cannot migrate malformed board line {} in {}: {}",
                            line_num + 1,
                            path.display(),
                            e
                        )));
                    }
                    eprintln!(
                        "Warning: Skipping malformed line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                }
            }
        }

        Ok(issues)
    }

    /// Append a new issue to issues.jsonl with exclusive file lock.
    /// Acquire the board-wide mutation lock.
    ///
    /// Every mutating operation must hold this for its FULL read-modify-write
    /// span. Per-file locks are not enough: rewrite paths build a new file and
    /// rename it over the board, so a writer locking only its own temp file
    /// excludes nobody, and two concurrent mutations silently revert each
    /// other (observed live 2026-07-22: a `done` lost to a description edit).
    /// The lock releases when the returned handle drops.
    fn lock_board(&self) -> Result<File> {
        self.validate_storage_root()?;
        let lock_path = self.board_lock_path();
        let lock_file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(false)
            .open(&lock_path)?;
        lock_file
            .lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;
        Ok(lock_file)
    }

    /// Run an arbitrary board-scoped operation while holding the same lock as
    /// issue lifecycle mutations.
    ///
    /// Durable adjuncts such as the federation manifest must share this lock
    /// with `issues.jsonl`: their validation reads issue ownership and their
    /// write must not race a claim, completion, or deletion between those two
    /// steps. The closure is responsible for re-reading every file it uses
    /// after the lock is acquired.
    pub fn with_board_lock<T, F>(&self, operation: F) -> Result<T>
    where
        F: FnOnce() -> Result<T>,
    {
        let _board_lock = self.lock_board()?;
        operation()
    }

    /// Run the file half of an authenticated board-initialization journal
    /// under the same board-wide lock as every ordinary mutation. The journal
    /// writer creates `.manna/` before calling this method, but durable board
    /// files may not exist yet. That is why this boundary cannot require an
    /// initialized issues file the way row transactions do.
    pub fn recover_initialize_with<F>(&self, install: F) -> Result<()>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let _board_lock = self.lock_board()?;
        install().map_err(MannaError::MutationRejected)
    }

    pub fn append_issue(&self, issue: &Issue) -> Result<()> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let _board_lock = self.lock_board()?;
        let issues = self.load_issues()?;
        if issues.iter().any(|existing| existing.id == issue.id) {
            return Err(MannaError::IssueAlreadyExists(issue.id.clone()));
        }
        if self.board_is_strict()? {
            let mut proposed = issues.clone();
            proposed.push(issue.clone());
            Self::validate_strict_row_shapes(&proposed)?;
        }

        let file = OpenOptions::new().append(true).open(&path)?;

        // Acquire exclusive lock
        file.lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;

        // Write issue as JSON line
        let mut writer = std::io::BufWriter::new(&file);
        serde_json::to_writer(&mut writer, issue)?;
        writeln!(writer)?;
        writer.flush()?;

        // Lock is released when file is dropped
        Ok(())
    }

    fn write_issues_locked(&self, issues: &[Issue]) -> Result<()> {
        let path = self.issues_path();
        let mut nonce = [0_u8; 16];
        OsRng.fill_bytes(&mut nonce);
        let suffix = nonce
            .iter()
            .map(|byte| format!("{:02x}", byte))
            .collect::<String>();
        let temp_path = self.manna_dir().join(format!(
            ".issues.jsonl.{}.{}.tmp",
            std::process::id(),
            suffix
        ));
        {
            let temp_file = OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&temp_path)?;

            // Acquire exclusive lock on temp file
            if let Err(error) = temp_file.lock_exclusive() {
                let _ = fs::remove_file(&temp_path);
                return Err(MannaError::LockFailed(error.to_string()));
            }

            let write_result = (|| -> Result<()> {
                let mut writer = std::io::BufWriter::new(&temp_file);
                for issue in issues {
                    serde_json::to_writer(&mut writer, issue)?;
                    writeln!(writer)?;
                }
                writer.flush()?;
                temp_file.sync_all()?;
                Ok(())
            })();
            if let Err(error) = write_result {
                let _ = fs::remove_file(&temp_path);
                return Err(error);
            }
        }

        if let Err(error) = fs::rename(&temp_path, &path) {
            let _ = fs::remove_file(&temp_path);
            return Err(error.into());
        }
        if let Some(parent) = path.parent() {
            File::open(parent)?.sync_all()?;
        }

        Ok(())
    }

    fn mutate_issue_locked<F>(&self, id: &str, mutation: F) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let snapshot = issues.clone();
        let issue = issues
            .iter_mut()
            .find(|issue| issue.id == id)
            .ok_or_else(|| MannaError::IssueNotFound(id.to_string()))?;
        mutation(issue, &snapshot).map_err(MannaError::MutationRejected)?;
        issue.validate().map_err(MannaError::MutationRejected)?;
        let updated = issue.clone();
        if self.board_is_strict()? {
            Self::validate_strict_row_shapes(&issues)?;
        }
        self.write_issues_locked(&issues)?;
        Ok(updated)
    }

    /// Claim an issue under one board lock. The row is reloaded only after
    /// the lock is held, so exactly one contender can observe `open`.
    pub fn claim_issue(&self, id: &str, session: &SessionIdentity) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| issue.claim(session))
    }

    /// Claim with an integrity precondition evaluated after acquiring the
    /// board lock and reloading the row. This closes the validate-then-claim
    /// race as well as the open-then-write race.
    pub fn claim_issue_checked<F>(
        &self,
        id: &str,
        session: &SessionIdentity,
        precondition: F,
    ) -> Result<Issue>
    where
        F: FnOnce(&Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, |issue, issues| {
            precondition(issue, issues)?;
            issue.claim(session)
        })
    }

    /// Complete a claimed issue only for the session that owns it.
    pub fn complete_issue(&self, id: &str, session: &SessionIdentity) -> Result<Issue> {
        self.complete_issue_checked(id, session, |_, _| Ok(()))
            .map(|completed| completed.issue)
    }

    /// Complete only after rechecking an external integrity precondition under
    /// the same board lock as the lifecycle transition. Strict workflows use
    /// this to prevent `done` from hiding a handoff edit made after claim.
    /// Removing the completed blocker from every dependent shares that lock
    /// and atomic write, so readers never observe a half-completed cascade.
    pub fn complete_issue_checked<F>(
        &self,
        id: &str,
        session: &SessionIdentity,
        precondition: F,
    ) -> Result<CompletedIssue>
    where
        F: FnOnce(&Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        if !self.issues_path().exists() {
            return Err(MannaError::NotInitialized);
        }

        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let index = issues
            .iter()
            .position(|issue| issue.id == id)
            .ok_or_else(|| MannaError::IssueNotFound(id.to_string()))?;
        let mut issue = issues[index].clone();
        if issue.issue_type == crate::issue::IssueType::Dream {
            issue.close_dream(session)
        } else {
            precondition(&issue, &issues).map_err(MannaError::MutationRejected)?;
            issue.complete(session)
        }
        .map_err(MannaError::MutationRejected)?;
        issue.validate().map_err(MannaError::MutationRejected)?;
        issues[index] = issue.clone();

        let mut released = Vec::new();
        for dependent in &mut issues {
            if !dependent.blocked_by.iter().any(|blocker| blocker == id) {
                continue;
            }
            let was_blocked = dependent.status == IssueStatus::Blocked;
            dependent.blocked_by.retain(|blocker| blocker != id);
            dependent.update_blocked_status();
            dependent.updated_at = issue.updated_at;
            dependent.validate().map_err(MannaError::MutationRejected)?;
            if was_blocked && dependent.blocked_by.is_empty() {
                released.push(dependent.id.clone());
            }
        }
        if self.board_is_strict()? {
            Self::validate_strict_row_shapes(&issues)?;
        }
        self.write_issues_locked(&issues)?;
        Ok(CompletedIssue {
            issue: issues[index].clone(),
            released,
        })
    }

    /// Release a claimed issue only for the session that owns it.
    pub fn release_issue(&self, id: &str, session: &SessionIdentity) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| issue.release(session))
    }

    /// Mutate metadata without allowing a caller to smuggle a lifecycle
    /// transition through an update path.
    pub fn mutate_issue_metadata<F>(
        &self,
        id: &str,
        session: &SessionIdentity,
        mutation: F,
    ) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, |issue, issues| {
            issue.require_owner(session)?;
            let binding_metadata = (
                issue.issue_type,
                issue.title.clone(),
                issue.description.clone(),
                issue.track.clone(),
                issue.source.clone(),
                issue.prompt.clone(),
                issue.handoff_digest.clone(),
            );
            let lifecycle = (
                issue.status.clone(),
                issue.claimed_by.clone(),
                issue.claimed_at,
                issue.claim_token_hash.clone(),
                issue.blocked_by.clone(),
            );
            mutation(issue, issues)?;
            if binding_metadata.5.is_some()
                && binding_metadata.6.is_some()
                && binding_metadata
                    != (
                        issue.issue_type,
                        issue.title.clone(),
                        issue.description.clone(),
                        issue.track.clone(),
                        issue.source.clone(),
                        issue.prompt.clone(),
                        issue.handoff_digest.clone(),
                    )
            {
                return Err(
                    "bound item metadata must change through the handoff transaction".to_string(),
                );
            }
            if lifecycle
                != (
                    issue.status.clone(),
                    issue.claimed_by.clone(),
                    issue.claimed_at,
                    issue.claim_token_hash.clone(),
                    issue.blocked_by.clone(),
                )
            {
                return Err(
                    "metadata update attempted to bypass a lifecycle transition".to_string()
                );
            }
            Ok(())
        })
    }

    pub fn add_blocker(
        &self,
        id: &str,
        blocker_id: &str,
        session: &SessionIdentity,
    ) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, issues| {
            issue.require_owner(session)?;
            if !issues.iter().any(|candidate| candidate.id == blocker_id) {
                return Err(format!("Blocker issue {} not found", blocker_id));
            }
            issue.add_blocker(blocker_id.to_string());
            Ok(())
        })
    }

    pub fn remove_blocker(
        &self,
        id: &str,
        blocker_id: &str,
        session: &SessionIdentity,
    ) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| {
            issue.require_owner(session)?;
            issue.remove_blocker(blocker_id);
            Ok(())
        })
    }

    /// Reconcile-only mutation path. Callers must first prove the repair from
    /// external evidence, such as a dead pinned session or a resolved blocker.
    pub fn repair_issue<F>(&self, id: &str, mutation: F) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, mutation)
    }

    /// Replace a row only when recovery can prove the existing record has the
    /// same identity. Used by the pair transaction journal.
    pub fn recover_issue(&self, expected: &Issue) -> Result<Issue> {
        self.recover_issue_with(expected, || Ok(()))
    }

    pub fn recover_issue_with<F>(&self, expected: &Issue, commit_pair: F) -> Result<Issue>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        if let Some(existing) = issues.iter().find(|issue| issue.id == expected.id) {
            if existing == expected {
                commit_pair().map_err(MannaError::MutationRejected)?;
                return Ok(existing.clone());
            }
            return Err(MannaError::RecoveryConflict(format!(
                "transaction recovery found a conflicting row for {}",
                expected.id
            )));
        }
        expected.validate().map_err(MannaError::MutationRejected)?;
        commit_pair().map_err(MannaError::MutationRejected)?;
        issues.push(expected.clone());
        self.write_issues_locked(&issues)?;
        Ok(expected.clone())
    }

    /// Replace one row during a recoverable pair attach/detach operation.
    pub fn recover_replace_issue(&self, expected_before: &Issue, after: &Issue) -> Result<Issue> {
        self.recover_replace_issue_with(expected_before, after, || Ok(()))
    }

    pub fn recover_replace_issue_with<F>(
        &self,
        expected_before: &Issue,
        after: &Issue,
        commit_pair: F,
    ) -> Result<Issue>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let row = issues
            .iter_mut()
            .find(|issue| issue.id == expected_before.id)
            .ok_or_else(|| {
                MannaError::RecoveryConflict(format!(
                    "transaction recovery found no row for {}",
                    expected_before.id
                ))
            })?;
        if row != expected_before {
            if row == after {
                commit_pair().map_err(MannaError::MutationRejected)?;
                return Ok(row.clone());
            }
            return Err(MannaError::RecoveryConflict(format!(
                "transaction recovery found concurrent changes to {}",
                expected_before.id
            )));
        }
        commit_pair().map_err(MannaError::MutationRejected)?;
        *row = after.clone();
        row.validate().map_err(MannaError::MutationRejected)?;
        self.write_issues_locked(&issues)?;
        Ok(after.clone())
    }

    /// Replace the complete board under one lock while a workflow transaction
    /// prepares its file side and publishes board identity last. Recovery may
    /// observe either the exact before or exact after board; any third state is
    /// a concurrent change and is never overwritten.
    pub fn recover_replace_board_with<Prepare, Publish>(
        &self,
        expected_before: &[Issue],
        after: &[Issue],
        prepare_files: Prepare,
        publish_identity: Publish,
    ) -> Result<()>
    where
        Prepare: FnOnce() -> std::result::Result<(), String>,
        Publish: FnOnce() -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        for issue in after {
            issue.validate().map_err(MannaError::MutationRejected)?;
        }

        let _board_lock = self.lock_board()?;
        let current = self.load_issues_strict()?;
        if current != expected_before && current != after {
            return Err(MannaError::RecoveryConflict(
                "board transaction recovery found concurrent row changes".to_string(),
            ));
        }

        prepare_files().map_err(MannaError::MutationRejected)?;
        if current == expected_before {
            self.write_issues_locked(after)?;
        }
        publish_identity().map_err(MannaError::MutationRejected)?;
        Ok(())
    }

    /// Roll back the file half of a whole-board transaction only while the
    /// board is provably in a third, concurrently advanced state. The lock
    /// prevents another board writer from racing between that proof and the
    /// rollback. If the board returned to either authenticated transaction
    /// state, recovery must retry instead of undoing a valid commit.
    pub fn recover_rollback_board_files<Rollback>(
        &self,
        expected_before: &[Issue],
        expected_after: &[Issue],
        rollback_files: Rollback,
    ) -> Result<()>
    where
        Rollback: FnOnce() -> std::result::Result<(), String>,
    {
        let _board_lock = self.lock_board()?;
        let current = self.load_issues_strict()?;
        if current == expected_before || current == expected_after {
            return Err(MannaError::RecoveryConflict(
                "board returned to an authenticated transaction state during rollback".to_string(),
            ));
        }
        rollback_files().map_err(MannaError::MutationRejected)
    }

    /// Delete an issue under the board lock after enforcing current-session
    /// ownership. Pair-aware callers archive the handoff first through the
    /// workflow transaction journal.
    pub fn delete_issue_owned(&self, id: &str, session: &SessionIdentity) -> Result<Issue> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let index = issues
            .iter()
            .position(|issue| issue.id == id)
            .ok_or_else(|| MannaError::IssueNotFound(id.to_string()))?;
        issues[index]
            .require_owner(session)
            .map_err(MannaError::MutationRejected)?;
        if self.board_is_strict()?
            && issues[index].issue_type == crate::issue::IssueType::Item
            && (issues[index].prompt.is_some() || issues[index].handoff_digest.is_some())
        {
            return Err(MannaError::MutationRejected(
                "bound strict item deletion must archive through the handoff transaction"
                    .to_string(),
            ));
        }
        let removed = issues.remove(index);
        self.write_issues_locked(&issues)?;
        Ok(removed)
    }

    /// Delete an exact transaction row idempotently.
    pub fn recover_delete_issue(&self, expected: &Issue) -> Result<()> {
        self.recover_delete_issue_with(expected, || Ok(()))
    }

    pub fn recover_delete_issue_with<F>(&self, expected: &Issue, commit_pair: F) -> Result<()>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let Some(index) = issues.iter().position(|issue| issue.id == expected.id) else {
            commit_pair().map_err(MannaError::MutationRejected)?;
            return Ok(());
        };
        let current = &issues[index];
        if current != expected {
            return Err(MannaError::RecoveryConflict(format!(
                "transaction recovery found a conflicting row for {}",
                expected.id
            )));
        }
        commit_pair().map_err(MannaError::MutationRejected)?;
        issues.remove(index);
        self.write_issues_locked(&issues)?;

        Ok(())
    }

    /// Load all session events from sessions.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_sessions(&self) -> Result<Vec<SessionEvent>> {
        self.validate_storage_root()?;
        let path = self.sessions_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = File::open(&path)?;
        let reader = BufReader::new(file);
        let mut events = Vec::new();

        for (line_num, line_result) in reader.lines().enumerate() {
            let line = match line_result {
                Ok(l) => l,
                Err(e) => {
                    eprintln!(
                        "Warning: Failed to read line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                    continue;
                }
            };

            // Skip empty lines
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<SessionEvent>(&line) {
                Ok(event) => events.push(event),
                Err(e) => {
                    eprintln!(
                        "Warning: Skipping malformed line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                }
            }
        }

        Ok(events)
    }

    /// Append a session event to sessions.jsonl with exclusive file lock.
    pub fn append_session(&self, event: &SessionEvent) -> Result<()> {
        self.validate_storage_root()?;
        let path = self.sessions_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = OpenOptions::new().append(true).open(&path)?;

        // Acquire exclusive lock
        file.lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;

        // Write event as JSON line
        let mut writer = std::io::BufWriter::new(&file);
        serde_json::to_writer(&mut writer, event)?;
        writeln!(writer)?;
        writer.flush()?;

        // Lock is released when file is dropped
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use tempfile::TempDir;

    fn session(id: &str) -> SessionIdentity {
        SessionIdentity::from_token(id, &format!("{}-0123456789abcdef0123456789abcdef", id))
            .unwrap()
    }

    fn setup_store() -> (TempDir, MannaStore) {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());
        store.init().unwrap();
        (temp_dir, store)
    }

    #[test]
    fn test_init_creates_directory_and_files() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        assert!(!store.is_initialized());

        store.init().unwrap();

        assert!(store.is_initialized());
        assert!(store.manna_dir().exists());
        assert!(store.issues_path().exists());
        assert!(store.sessions_path().exists());
    }

    #[test]
    fn test_init_is_idempotent() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        // First init
        store.init().unwrap();

        // Second init should not error
        store.init().unwrap();

        assert!(store.is_initialized());
    }

    #[test]
    #[cfg(unix)]
    fn init_rejects_a_symlinked_manna_root() {
        use std::os::unix::fs::symlink;

        let project = TempDir::new().unwrap();
        let outside = TempDir::new().unwrap();
        symlink(outside.path(), project.path().join(".manna")).unwrap();
        let store = MannaStore::new(project.path());
        let error = store.init().unwrap_err().to_string();
        assert!(error.contains("symlinked Manna storage path"));
        assert!(!outside.path().join("issues.jsonl").exists());
    }

    #[test]
    #[cfg(unix)]
    fn mutation_rejects_a_symlinked_board_lock() {
        use std::os::unix::fs::symlink;

        let (_temp, store) = setup_store();
        let outside = TempDir::new().unwrap();
        let outside_lock = outside.path().join("outside.lock");
        File::create(&outside_lock).unwrap();
        symlink(&outside_lock, store.board_lock_path()).unwrap();
        let issue = Issue::new("mn-lock01".to_string(), "Protected lock".to_string()).unwrap();
        let error = store.append_issue(&issue).unwrap_err().to_string();
        assert!(error.contains("symlinked Manna storage path"));
        assert!(store
            .load_issues()
            .unwrap_err()
            .to_string()
            .contains("symlinked"));
    }

    #[test]
    fn test_append_and_load_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-abc123".to_string(), "Test issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].id, "mn-abc123");
        assert_eq!(issues[0].title, "Test issue");
    }

    #[test]
    fn test_append_multiple_issues() {
        let (_temp_dir, store) = setup_store();

        let issue1 = Issue::new("mn-111111".to_string(), "First".to_string()).unwrap();
        let issue2 = Issue::new("mn-222222".to_string(), "Second".to_string()).unwrap();
        let issue3 = Issue::new("mn-333333".to_string(), "Third".to_string()).unwrap();

        store.append_issue(&issue1).unwrap();
        store.append_issue(&issue2).unwrap();
        store.append_issue(&issue3).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 3);
        assert_eq!(issues[0].id, "mn-111111");
        assert_eq!(issues[1].id, "mn-222222");
        assert_eq!(issues[2].id, "mn-333333");
    }

    #[test]
    fn test_update_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-update".to_string(), "Original".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        store
            .mutate_issue_metadata("mn-update", &session("ses-test"), |issue, _| {
                issue.title = "Updated".to_string();
                Ok(())
            })
            .unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].title, "Updated");
    }

    #[test]
    fn test_update_nonexistent_issue_fails() {
        let (_temp_dir, store) = setup_store();

        let result = store.mutate_issue_metadata("mn-ghost", &session("ses-test"), |_, _| Ok(()));
        assert!(matches!(result, Err(MannaError::IssueNotFound(_))));
    }

    #[test]
    fn test_skip_malformed_lines() {
        let (_temp_dir, store) = setup_store();

        // Write a valid issue
        let issue = Issue::new("mn-valid".to_string(), "Valid".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        // Manually append a malformed line
        let path = store.issues_path();
        let mut file = OpenOptions::new().append(true).open(&path).unwrap();
        writeln!(file, "{{not valid json").unwrap();

        // Append another valid issue
        let issue2 = Issue::new("mn-valid2".to_string(), "Valid2".to_string()).unwrap();
        store.append_issue(&issue2).unwrap();

        // Should load both valid issues, skipping the malformed line
        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 2);
        assert_eq!(issues[0].id, "mn-valid");
        assert_eq!(issues[1].id, "mn-valid2");
    }

    #[test]
    fn test_append_and_load_session() {
        let (_temp_dir, store) = setup_store();

        let event = SessionEvent::start("ses_123".to_string(), serde_json::json!({}));
        store.append_session(&event).unwrap();

        let events = store.load_sessions().unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].session_id, "ses_123");
    }

    #[test]
    fn test_concurrent_writes_dont_corrupt() {
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();

        let mut handles = vec![];

        // Spawn 10 threads, each writing 10 issues
        for thread_id in 0..10 {
            let store_clone = Arc::clone(&store);
            let handle = thread::spawn(move || {
                for i in 0..10 {
                    let issue = Issue::new(
                        format!("mn-t{:02}i{:02}", thread_id, i),
                        format!("Thread {} Issue {}", thread_id, i),
                    )
                    .unwrap();
                    store_clone.append_issue(&issue).unwrap();
                }
            });
            handles.push(handle);
        }

        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }

        // Verify all 100 issues are present and file is not corrupted
        let issues = store.load_issues().unwrap();
        assert_eq!(
            issues.len(),
            100,
            "Expected 100 issues, got {}",
            issues.len()
        );

        // Verify each issue is valid JSON and has correct format
        for issue in &issues {
            assert!(issue.id.starts_with("mn-"));
            assert!(!issue.title.is_empty());
        }
    }

    #[test]
    fn test_concurrent_claims_have_exactly_one_winner() {
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();
        store
            .append_issue(&Issue::new("mn-race01".to_string(), "Race".to_string()).unwrap())
            .unwrap();
        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for contender in 0..12 {
            let store = Arc::clone(&store);
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                barrier.wait();
                let identity = session(&format!("ses_{}", contender));
                store.claim_issue("mn-race01", &identity).is_ok()
            }));
        }
        let wins = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .filter(|won| *won)
            .count();
        assert_eq!(wins, 1);
        let issue = store.load_issues().unwrap().pop().unwrap();
        assert_eq!(issue.status, crate::issue::IssueStatus::InProgress);
        assert!(issue.claimed_by.is_some());
    }

    #[test]
    fn test_metadata_update_rejects_non_owner() {
        let (_temp_dir, store) = setup_store();
        store
            .append_issue(&Issue::new("mn-owner1".to_string(), "Owned".to_string()).unwrap())
            .unwrap();
        store
            .claim_issue("mn-owner1", &session("ses_owner"))
            .unwrap();
        let result =
            store.mutate_issue_metadata("mn-owner1", &session("ses_intruder"), |issue, _| {
                issue.title = "Hijacked".to_string();
                Ok(())
            });
        assert!(matches!(result, Err(MannaError::MutationRejected(_))));
        assert_eq!(store.load_issues().unwrap()[0].title, "Owned");
    }

    fn completion_board() -> (TempDir, MannaStore, SessionIdentity) {
        let (temp, store) = setup_store();
        let owner = session("ses_completion");
        for id in ["mn-first", "mn-second", "mn-single", "mn-multi", "mn-other"] {
            store
                .append_issue(&Issue::new(id.to_string(), id.to_string()).unwrap())
                .unwrap();
        }
        for id in ["mn-first", "mn-second"] {
            store.claim_issue(id, &owner).unwrap();
        }
        for (dependent, blocker) in [
            ("mn-single", "mn-first"),
            ("mn-multi", "mn-first"),
            ("mn-multi", "mn-second"),
        ] {
            store.add_blocker(dependent, blocker, &owner).unwrap();
        }
        (temp, store, owner)
    }

    #[test]
    fn completion_releases_only_dependents_with_no_remaining_blockers() {
        let (_temp, store, owner) = completion_board();
        let before = store.load_issues().unwrap();
        let first = store
            .complete_issue_checked("mn-first", &owner, |_, _| Ok(()))
            .unwrap();
        assert_eq!(first.issue.status, IssueStatus::Done);
        assert_eq!(first.released, ["mn-single"]);

        let after = store.load_issues().unwrap();
        assert_eq!(after[2].status, IssueStatus::Open);
        assert!(after[2].blocked_by.is_empty());
        assert_eq!(after[3].status, IssueStatus::Blocked);
        assert_eq!(after[3].blocked_by, ["mn-second"]);
        assert_eq!(after[2].updated_at, first.issue.updated_at);
        assert_eq!(after[3].updated_at, first.issue.updated_at);
        assert_eq!(after[1], before[1]);
        assert_eq!(after[4], before[4]);

        let second = store
            .complete_issue_checked("mn-second", &owner, |_, _| Ok(()))
            .unwrap();
        assert_eq!(second.released, ["mn-multi"]);
        let after_second = store.load_issues().unwrap();
        assert_eq!(after_second[3].status, IssueStatus::Open);
        assert!(after_second[3].blocked_by.is_empty());
        assert_eq!(after_second[2], after[2]);
        assert_eq!(after_second[4], before[4]);
        store.claim_issue("mn-multi", &owner).unwrap();
    }

    #[test]
    fn completion_preserves_dependent_ownership_and_closed_status() {
        let (_temp, store, owner) = completion_board();
        let other_owner = session("ses_other_owner");
        store.claim_issue("mn-other", &other_owner).unwrap();
        let claimed = store
            .add_blocker("mn-other", "mn-first", &other_owner)
            .unwrap();
        store.complete_issue("mn-second", &owner).unwrap();
        store.add_blocker("mn-second", "mn-first", &owner).unwrap();

        let completed = store
            .complete_issue_checked("mn-first", &owner, |_, _| Ok(()))
            .unwrap();
        assert_eq!(completed.released, ["mn-single", "mn-multi", "mn-other"]);
        let after = store.load_issues().unwrap();
        assert_eq!(after[1].status, IssueStatus::Done);
        assert!(after[1].blocked_by.is_empty());
        assert_eq!(after[4].status, IssueStatus::InProgress);
        assert!(after[4].blocked_by.is_empty());
        assert_eq!(after[4].claimed_by, claimed.claimed_by);
        assert_eq!(after[4].claimed_at, claimed.claimed_at);
        assert_eq!(after[4].claim_token_hash, claimed.claim_token_hash);
    }

    #[test]
    fn completion_refusals_leave_the_entire_board_unchanged() {
        let (_temp, store, owner) = completion_board();
        let before = fs::read(store.issues_path()).unwrap();
        let refused = store.complete_issue("mn-first", &session("ses_intruder"));
        assert!(matches!(refused, Err(MannaError::MutationRejected(_))));
        assert_eq!(fs::read(store.issues_path()).unwrap(), before);

        let refused = store.complete_issue_checked("mn-first", &owner, |_, _| {
            Err("handoff binding is stale".to_string())
        });
        assert!(matches!(refused, Err(MannaError::MutationRejected(_))));
        assert_eq!(fs::read(store.issues_path()).unwrap(), before);

        let refused = store.complete_issue("mn-other", &owner);
        assert!(matches!(refused, Err(MannaError::MutationRejected(_))));
        assert_eq!(fs::read(store.issues_path()).unwrap(), before);
    }

    #[test]
    fn completion_removes_all_occurrences_without_sweeping_missing_blockers() {
        let (_temp, store, owner) = completion_board();
        let mut rows = store.load_issues().unwrap();
        rows[2].blocked_by.push("mn-first".to_string());
        rows[3].blocked_by.push("mn-missing".to_string());
        // Legacy or hand-edited board fixture, never a production mutation.
        store.write_issues_locked(&rows).unwrap();

        let completed = store
            .complete_issue_checked("mn-first", &owner, |_, _| Ok(()))
            .unwrap();
        assert_eq!(completed.released, ["mn-single"]);
        store.complete_issue("mn-second", &owner).unwrap();
        let after = store.load_issues().unwrap();
        assert!(after[2].blocked_by.is_empty());
        assert_eq!(after[3].blocked_by, ["mn-missing"]);
        assert_eq!(after[3].status, IssueStatus::Blocked);
    }

    #[test]
    fn completion_of_concurrent_blockers_releases_shared_dependent_once() {
        let (_temp, store, owner) = completion_board();
        let barrier = Arc::new(Barrier::new(2));
        let handles: Vec<_> = ["mn-first", "mn-second"]
            .into_iter()
            .map(|id| {
                let store = store.clone();
                let owner = owner.clone();
                let barrier = Arc::clone(&barrier);
                thread::spawn(move || {
                    barrier.wait();
                    store
                        .complete_issue_checked(id, &owner, |_, _| Ok(()))
                        .unwrap()
                        .released
                })
            })
            .collect();
        let mut released: Vec<_> = handles
            .into_iter()
            .flat_map(|handle| handle.join().unwrap())
            .collect();
        released.sort();
        assert_eq!(released, ["mn-multi", "mn-single"]);
        let after = store.load_issues().unwrap();
        assert_eq!(after[0].status, IssueStatus::Done);
        assert_eq!(after[1].status, IssueStatus::Done);
        for dependent in &after[2..4] {
            assert!(dependent.blocked_by.is_empty());
            assert_eq!(dependent.status, IssueStatus::Open);
        }
    }

    #[test]
    fn transaction_create_replay_requires_the_complete_row() {
        let (_temp, store) = setup_store();
        let mut existing = Issue::new("mn-row001".to_string(), "Original".to_string()).unwrap();
        existing.prompt = Some(".handoff/mn-row001-original.md".to_string());
        existing.handoff_digest = Some(format!("sha256:{}", "a".repeat(64)));
        store.append_issue(&existing).unwrap();

        let mut forged = existing.clone();
        forged.title = "Different metadata".to_string();
        let mut pair_committed = false;
        let result = store.recover_issue_with(&forged, || {
            pair_committed = true;
            Ok(())
        });
        assert!(matches!(result, Err(MannaError::RecoveryConflict(_))));
        assert!(!pair_committed);
        assert_eq!(store.load_issues().unwrap()[0], existing);
    }

    #[test]
    fn transaction_update_replay_requires_the_complete_after_row() {
        let (_temp, store) = setup_store();
        let mut before = Issue::new("mn-row002".to_string(), "Before".to_string()).unwrap();
        before.prompt = Some(".handoff/mn-row002-before.md".to_string());
        before.handoff_digest = Some(format!("sha256:{}", "b".repeat(64)));
        store.append_issue(&before).unwrap();
        let mut after = before.clone();
        after.title = "After".to_string();
        after.updated_at = chrono::Utc::now();
        store.recover_replace_issue(&before, &after).unwrap();

        let mut forged_after = after.clone();
        forged_after.description = Some("metadata omitted by the old replay check".to_string());
        let result = store.recover_replace_issue(&before, &forged_after);
        assert!(matches!(result, Err(MannaError::RecoveryConflict(_))));
        assert_eq!(store.load_issues().unwrap()[0], after);
    }

    #[test]
    fn test_concurrent_mutations_lose_no_writes() {
        // The 2026-07-22 incident class: rewrite paths (update/delete) built
        // from a stale load used to revert concurrent writers at rename time.
        // Ten threads each own one issue and update it 20 times while other
        // threads do the same; every issue must end at its final value, and
        // interleaved appends must all survive the rewrites.
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();

        for t in 0..10 {
            let issue = Issue::new(format!("mn-mut{:03}", t), format!("Mutator {}", t)).unwrap();
            store.append_issue(&issue).unwrap();
        }

        let mut handles = vec![];
        for t in 0..10 {
            let store_clone = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for round in 1..=20 {
                    let id = format!("mn-mut{:03}", t);
                    store_clone
                        .mutate_issue_metadata(&id, &session("ses-test"), |issue, _| {
                            issue.title = format!("Mutator {} round {}", t, round);
                            Ok(())
                        })
                        .unwrap();
                }
            }));
        }
        // Appenders race the rewriters: their rows must never vanish.
        for a in 0..4 {
            let store_clone = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for i in 0..5 {
                    let issue = Issue::new(
                        format!("mn-app{}{:02}", a, i),
                        format!("Appender {} Issue {}", a, i),
                    )
                    .unwrap();
                    store_clone.append_issue(&issue).unwrap();
                }
            }));
        }
        for handle in handles {
            handle.join().unwrap();
        }

        let issues = store.load_issues().unwrap();
        assert_eq!(
            issues.len(),
            30,
            "lost rows: expected 30, got {}",
            issues.len()
        );
        for t in 0..10 {
            let issue = issues
                .iter()
                .find(|i| i.id == format!("mn-mut{:03}", t))
                .unwrap();
            assert_eq!(
                issue.title,
                format!("Mutator {} round 20", t),
                "lost update on {}",
                issue.id
            );
        }
    }

    #[test]
    fn test_not_initialized_errors() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        // Don't call init()

        let result = store.load_issues();
        assert!(matches!(result, Err(MannaError::NotInitialized)));

        let issue = Issue::new("mn-test".to_string(), "Test".to_string()).unwrap();
        let result = store.append_issue(&issue);
        assert!(matches!(result, Err(MannaError::NotInitialized)));
    }

    #[test]
    fn test_empty_file_loads_empty_vec() {
        let (_temp_dir, store) = setup_store();

        let issues = store.load_issues().unwrap();
        assert!(issues.is_empty());

        let sessions = store.load_sessions().unwrap();
        assert!(sessions.is_empty());
    }

    #[test]
    fn test_session_event_types() {
        let (_temp_dir, store) = setup_store();

        // Test all event types
        let start = SessionEvent::start("ses_1".to_string(), serde_json::json!({"key": "value"}));
        let claim = SessionEvent::claim("ses_1".to_string(), "mn-123".to_string());
        let release = SessionEvent::release("ses_1".to_string(), "mn-123".to_string());
        let done = SessionEvent::done("ses_1".to_string(), "mn-123".to_string());
        let end = SessionEvent::end("ses_1".to_string(), serde_json::json!({}));

        store.append_session(&start).unwrap();
        store.append_session(&claim).unwrap();
        store.append_session(&release).unwrap();
        store.append_session(&done).unwrap();
        store.append_session(&end).unwrap();

        let events = store.load_sessions().unwrap();
        assert_eq!(events.len(), 5);
    }
}
