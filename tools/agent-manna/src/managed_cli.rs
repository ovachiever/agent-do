//! CLI surface for the managed lifecycle: identity, coordinator grants,
//! submission, acceptance, release, closure assessment, audit history, and
//! the adoption doctor. Private helpers of the binary (output, identity,
//! coord liveness, trailer evidence) are reachable here because this is a
//! child module of `main`.
//!
//! Every mutation is one locked transaction over the board row and the
//! managed sidecar: the row is reloaded under the lock, the grant is
//! re-resolved against that row (a revoked grant or a changed scope does not
//! carry an earlier look forward), the expected owner and attempt are
//! compared, and only then is anything written.

use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use clap::Subcommand;
use serde::Serialize;

use manna_core::error::MannaError;
use manna_core::issue::{Issue, IssueStatus, IssueType, SessionIdentity};
use manna_core::managed::{
    assessment_token, closable_hex, closure_blockers, grant_id, parse_assessment_token,
    revalidate_authority, submission_id, transaction_id, Acceptance, AssessmentConditions,
    Authority, Correction, Grant, GrantFile, GrantScope, Intent, LifecycleEvent, ManagedRecord,
    ManagedStore, PinnedTarget, Release, Revocation, Submission, BOARD_SCOPE, CAPABILITY,
};
use manna_core::reconcile::manna_trailer_ids;
use manna_core::state::direct_coord_program;
use manna_core::store::MannaStore;

use crate::{
    commit_touches_source, coord_peer_statuses_all, find_issue, handle_manna_error,
    load_board_workflow, output_error, output_error_json, output_success, output_success_json,
    require_session_identity, IssueData, EXIT_NEEDS_AUTHORIZATION, EXIT_USER_ERROR,
};

/// Test seam: `MANNA_MANAGED_FAULT=after_release_pending` ends the process
/// right after a release's pending phase is durable and before the row's
/// claim is released, so the recovery path can be exercised for real.
/// `after_board_intent` ends a grant or revocation right after its intent
/// is durable and before the grants file or the audit is written.
const FAULT_ENV: &str = "MANNA_MANAGED_FAULT";

#[derive(Subcommand)]
pub enum CoordinatorCommands {
    /// Grant scoped coordinator authority to a session (operator only)
    Grant {
        /// The coordinator's public session label (`manna identity` prints it)
        #[arg(long)]
        session: String,
        /// The coordinator's ownership proof (`manna identity` prints it)
        #[arg(long)]
        proof: String,
        /// Item ids the grant covers (repeatable)
        #[arg(long = "item")]
        items: Vec<String>,
        /// Track ids the grant covers (repeatable)
        #[arg(long = "track")]
        tracks: Vec<String>,
        /// Why this session coordinates this scope
        #[arg(long)]
        reason: String,
        #[arg(long)]
        json: bool,
    },
    /// Revoke a grant (operator only); the record stays in history
    Revoke {
        grant_id: String,
        #[arg(long)]
        reason: String,
        #[arg(long)]
        json: bool,
    },
    /// List grants, live and revoked
    List {
        #[arg(long)]
        json: bool,
    },
}

#[derive(Subcommand)]
pub enum ManagedCommands {
    /// Put an item under coordinator-owned closure with named required checks
    Require {
        id: String,
        /// A check that must carry an acceptance before closure (repeatable)
        #[arg(long = "check", required = true)]
        checks: Vec<String>,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        json: bool,
    },
    /// Request a correction on the current submission (coordinator)
    Correct {
        id: String,
        #[arg(long)]
        reason: String,
        #[arg(long)]
        json: bool,
    },
    /// Release the current attempt so a replacement can claim (coordinator).
    /// Needs coord to have verified the worker dead or stopped, or a
    /// validated separate working tree for the replacement; also completes
    /// an interrupted release.
    Release {
        id: String,
        #[arg(long)]
        reason: String,
        /// A separate git working tree the replacement will work in; validated,
        /// never taken on its name
        #[arg(long)]
        isolated_checkout: Option<String>,
        #[arg(long)]
        json: bool,
    },
    /// Read one item's lifecycle audit
    History {
        id: String,
        #[arg(long)]
        json: bool,
    },
    /// Finish an incomplete transaction (state written but audit not, or the
    /// reverse) so the item can move again: operator, a granted coordinator,
    /// or the session that started it. `recover board` finishes a grant or
    /// revocation transaction (operator, or the session that started it)
    Recover {
        /// An item id, or `board` for a coordinator grant/revoke transaction
        id: String,
        #[arg(long)]
        json: bool,
    },
    /// Report what is installed, what is registered, and (with --probe) what
    /// was verified end to end on this machine
    Doctor {
        /// Run the managed lifecycle and the drop lifecycle through the real
        /// binaries and hooks in a throwaway fixture
        #[arg(long)]
        probe: bool,
        #[arg(long)]
        json: bool,
    },
}

#[derive(Serialize)]
struct IdentityData {
    session: String,
    proof: String,
    operator: bool,
    note: &'static str,
}

#[derive(Serialize)]
struct GrantData {
    grant: Grant,
}

#[derive(Serialize)]
struct GrantsData {
    grants: Vec<Grant>,
}

#[derive(Serialize)]
struct ManagedData {
    #[serde(flatten)]
    issue: IssueData,
    managed: ManagedRecord,
    authority: Authority,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    warnings: Vec<String>,
}

#[derive(Serialize)]
struct HistoryData {
    managed: Option<ManagedRecord>,
    events: Vec<LifecycleEvent>,
}

fn managed_store() -> ManagedStore {
    ManagedStore::new(Path::new("."))
}

fn emit<T: Serialize>(data: T, json: bool) -> ! {
    if json {
        output_success_json(data)
    } else {
        output_success(data)
    }
}

fn fail(message: &str, code: i32, json: bool) -> ! {
    if json {
        output_error_json(message, code)
    } else {
        output_error(message, code)
    }
}

fn now_label() -> DateTime<Utc> {
    Utc::now()
}

/// A rejected mutation is the caller's problem and prints in the format the
/// caller asked for; anything else is the store's and keeps the core's path.
fn rejected(error: MannaError, json: bool) -> ! {
    match error {
        MannaError::MutationRejected(message) => fail(&message, EXIT_USER_ERROR, json),
        other => handle_manna_error(other),
    }
}

fn lifecycle_event(
    action: &str,
    issue_id: &str,
    session: &SessionIdentity,
    authority: &str,
    attempt: Option<u32>,
    reason: Option<&str>,
    evidence: Option<&str>,
    detail: Option<serde_json::Value>,
) -> LifecycleEvent {
    LifecycleEvent {
        txn: String::new(),
        at: now_label(),
        action: action.to_string(),
        issue_id: issue_id.to_string(),
        actor: session.id().to_string(),
        authority: authority.to_string(),
        attempt,
        reason: reason.map(str::to_string),
        evidence: evidence.map(str::to_string),
        detail,
    }
}

/// Audit outside a transaction (claim notes only): a failure is reported,
/// never hidden.
fn audit_warning(store: &ManagedStore, event: &LifecycleEvent) -> Option<String> {
    store
        .append_event(event)
        .err()
        .map(|error| format!("lifecycle audit not written: {}", error))
}

/// Build a transaction intent: the complete outcome of one mutation, with
/// the audit line stamped with the transaction id.
fn intent_for(
    session: &SessionIdentity,
    issue_id: &str,
    mut event: LifecycleEvent,
    record_after: Option<ManagedRecord>,
    grants_after: Option<GrantFile>,
) -> Intent {
    let started_at = now_label();
    let txn = transaction_id(issue_id, &event.action, &started_at, session.id());
    event.txn = txn.clone();
    Intent {
        txn,
        issue_id: issue_id.to_string(),
        action: event.action.clone(),
        started_at,
        actor: session.id().to_string(),
        actor_proof: session.proof().to_string(),
        record_after,
        grants_after,
        event,
    }
}

/// The error a transaction leaves behind: the intent is durable, so the
/// outcome is recoverable, and the item refuses to move until it is.
fn transaction_failed(intent: &Intent, error: String) -> String {
    if intent.issue_id == BOARD_SCOPE {
        return format!(
            "transaction {} ({}) did not complete: {}. Its outcome is recorded; nothing managed moves and no grant changes until the operator runs `manna managed recover board`",
            intent.txn, intent.action, error
        );
    }
    format!(
        "transaction {} ({}) did not complete: {}. Its outcome is recorded; nothing else on {} moves until `manna managed recover {}` finishes it",
        intent.txn, intent.action, error, intent.issue_id, intent.issue_id
    )
}

fn load_grants_or_fail(store: &ManagedStore, json: bool) -> GrantFile {
    store
        .load_grants()
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json))
}

fn open_board() -> MannaStore {
    let store = MannaStore::new(Path::new("."));
    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }
    store
}

fn fault(point: &str) {
    if std::env::var(FAULT_ENV).ok().as_deref() == Some(point) {
        eprintln!("manna-core: injected fault `{}`; exiting before the next write", point);
        std::process::exit(70);
    }
}

/// Test seam: `MANNA_MANAGED_PAUSE_BEFORE_LOCK=<seconds>` holds a coordinator
/// mutation between its preview and the board lock, so a race with a writer
/// that changes the grants meanwhile can be reproduced deterministically.
const PAUSE_ENV: &str = "MANNA_MANAGED_PAUSE_BEFORE_LOCK";

fn pause_before_lock() {
    if let Some(seconds) = std::env::var(PAUSE_ENV)
        .ok()
        .and_then(|value| value.trim().parse::<f64>().ok())
        .filter(|seconds| *seconds > 0.0)
    {
        std::thread::sleep(std::time::Duration::from_secs_f64(seconds));
    }
}

// ----------------------------------------------------------------------------
// identity
// ----------------------------------------------------------------------------

pub fn cmd_identity(json: bool) -> ! {
    let session = require_session_identity();
    emit(
        IdentityData {
            session: session.id().to_string(),
            proof: session.proof().to_string(),
            operator: session.is_operator(),
            note: "the proof is a digest and safe to hand to the operator for `coordinator grant`; the token itself never prints",
        },
        json,
    )
}

// ----------------------------------------------------------------------------
// coordinator grants
// ----------------------------------------------------------------------------

pub fn cmd_coordinator(command: CoordinatorCommands) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let store = managed_store();
    match command {
        CoordinatorCommands::Grant {
            session: grantee,
            proof,
            items,
            tracks,
            reason,
            json,
        } => {
            let session = require_session_identity();
            if !session.is_operator() {
                fail(
                    "only the operator (your own terminal, no pinned agent identity) grants coordinator authority; a coordinator cannot grant itself",
                    EXIT_NEEDS_AUTHORIZATION,
                    json,
                );
            }
            if !proof.starts_with("sha256:") || proof.len() != 71 {
                fail(
                    "--proof must be the sha256:<64 hex> ownership proof that `manna identity` prints in the coordinator's session",
                    EXIT_USER_ERROR,
                    json,
                );
            }
            let scope = GrantScope { items, tracks };
            if scope.is_empty() {
                fail("a grant needs at least one --item or --track", EXIT_USER_ERROR, json);
            }
            for id in &scope.items {
                if !issues.iter().any(|issue| &issue.id == id) {
                    fail(&format!("item {} is not on this board", id), EXIT_USER_ERROR, json);
                }
            }
            for id in &scope.tracks {
                match issues.iter().find(|issue| &issue.id == id) {
                    Some(issue) if issue.issue_type == IssueType::Track => {}
                    Some(_) => fail(&format!("{} is not a track", id), EXIT_USER_ERROR, json),
                    None => fail(&format!("track {} is not on this board", id), EXIT_USER_ERROR, json),
                }
            }
            if reason.trim().is_empty() {
                fail("--reason must not be empty", EXIT_USER_ERROR, json);
            }
            let granted_at = now_label();
            let grant = Grant {
                id: grant_id(&grantee, &proof, &granted_at),
                coordinator_id: grantee,
                coordinator_proof: proof,
                scope,
                reason: reason.trim().to_string(),
                granted_at,
                granted_by: session.id().to_string(),
                revoked: None,
            };
            let written = grant.clone();
            let event = lifecycle_event(
                "grant",
                BOARD_SCOPE,
                &session,
                "operator",
                None,
                Some(&grant.reason),
                None,
                Some(serde_json::json!({"grant": grant.id, "coordinator": grant.coordinator_id, "scope": grant.scope})),
            );
            let result = board.with_board_lock(|| {
                if let Some(refusal) = store
                    .incomplete_transaction(BOARD_SCOPE)
                    .map_err(MannaError::MutationRejected)?
                {
                    return Err(MannaError::MutationRejected(refusal));
                }
                let mut grants = store.load_grants().map_err(MannaError::MutationRejected)?;
                if grants.grants.iter().any(|existing| existing.id == written.id) {
                    return Err(MannaError::MutationRejected(format!(
                        "grant {} already exists",
                        written.id
                    )));
                }
                grants.grants.push(written.clone());
                let intent = intent_for(&session, BOARD_SCOPE, event.clone(), None, Some(grants));
                store
                    .run_transaction(intent.clone())
                    .map_err(|error| MannaError::MutationRejected(transaction_failed(&intent, error)))?;
                Ok(())
            });
            if let Err(error) = result {
                rejected(error, json);
            }
            emit(GrantData { grant }, json)
        }
        CoordinatorCommands::Revoke { grant_id, reason, json } => {
            let session = require_session_identity();
            if !session.is_operator() {
                fail("only the operator revokes a grant", EXIT_NEEDS_AUTHORIZATION, json);
            }
            let actor = session.id().to_string();
            let reason_text = reason.trim().to_string();
            let revoked_id = grant_id.clone();
            let event = lifecycle_event(
                "revoke",
                BOARD_SCOPE,
                &session,
                "operator",
                None,
                Some(&reason_text),
                None,
                Some(serde_json::json!({"grant": grant_id})),
            );
            let result = board.with_board_lock(|| {
                if let Some(refusal) = store
                    .incomplete_transaction(BOARD_SCOPE)
                    .map_err(MannaError::MutationRejected)?
                {
                    return Err(MannaError::MutationRejected(refusal));
                }
                let mut grants = store.load_grants().map_err(MannaError::MutationRejected)?;
                let grant = grants
                    .grants
                    .iter_mut()
                    .find(|grant| grant.id == revoked_id)
                    .ok_or_else(|| MannaError::MutationRejected(format!("no grant {}", revoked_id)))?;
                if grant.revoked.is_some() {
                    return Err(MannaError::MutationRejected(format!(
                        "grant {} is already revoked",
                        revoked_id
                    )));
                }
                grant.revoked = Some(Revocation {
                    at: now_label(),
                    by: actor.clone(),
                    reason: reason_text.clone(),
                });
                let snapshot = grant.clone();
                let intent = intent_for(&session, BOARD_SCOPE, event.clone(), None, Some(grants));
                store
                    .begin_transaction(&intent)
                    .map_err(MannaError::MutationRejected)?;
                fault("after_board_intent");
                store
                    .finish_transaction(&intent)
                    .map_err(|error| MannaError::MutationRejected(transaction_failed(&intent, error)))?;
                Ok(snapshot)
            });
            let grant = match result {
                Ok(grant) => grant,
                Err(error) => rejected(error, json),
            };
            emit(GrantData { grant }, json)
        }
        CoordinatorCommands::List { json } => {
            let grants = load_grants_or_fail(&store, json);
            emit(GrantsData { grants: grants.grants }, json)
        }
    }
}

// ----------------------------------------------------------------------------
// managed records
// ----------------------------------------------------------------------------

/// A first look outside the lock, so an unauthorized caller gets a clear
/// refusal before any lock is taken. Every mutation re-derives this under
/// the lock against the reloaded row and grants; this is never the gate.
fn preview_coordination(
    session: &SessionIdentity,
    issue: &Issue,
    grants: &GrantFile,
    verb: &str,
    json: bool,
) -> Authority {
    match revalidate_authority(session, issue, grants, verb) {
        Ok(authority) => authority,
        Err(_) => {
            let authority = Authority::resolve(session, issue, grants);
            fail(
                &format!(
                    "{} needs coordinator authority over {}: an operator terminal or a live grant covering this item or its track and held by this session's proof (level here: {}). A coord role, a pulse row, or a claim label is not authority",
                    verb, issue.id, authority.level
                ),
                EXIT_NEEDS_AUTHORIZATION,
                json,
            )
        }
    }
}

/// One locked coordinator mutation over the managed record: grants are
/// reloaded and authority re-derived against the reloaded row, the record is
/// refused while a release is interrupted, the closure edits it, the sidecar
/// is saved, and the audit line is appended before the lock drops.
fn coordinator_mutation<F>(
    board: &MannaStore,
    store: &ManagedStore,
    id: &str,
    session: &SessionIdentity,
    verb: &str,
    edit: F,
) -> Result<(ManagedRecord, Authority, Vec<String>), MannaError>
where
    F: FnOnce(&Issue, &mut ManagedRecord, &Authority) -> Result<LifecycleEvent, String>,
{
    pause_before_lock();
    board.with_locked_issue(id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
        if let Some(refusal) = store.incomplete_transaction(id)? {
            return Err(refusal);
        }
        let grants = store.load_grants()?;
        let authority = revalidate_authority(session, current, &grants, verb)?;
        let mut managed = store.load_managed()?;
        let record = managed
            .items
            .get_mut(id)
            .ok_or_else(|| format!("{} is not a managed item", id))?;
        if record.release_interrupted(current) {
            return Err(format!(
                "{} has an interrupted release (attempt {} advanced, claim still on the row); a coordinator runs `manna managed release {} --reason <text>` to complete it before anything else",
                id,
                record.attempt.saturating_sub(1),
                id
            ));
        }
        let event = edit(current, record, &authority)?;
        let snapshot = record.clone();
        let intent = intent_for(session, id, event, Some(snapshot.clone()), None);
        store
            .run_transaction(intent.clone())
            .map_err(|error| transaction_failed(&intent, error))?;
        Ok((snapshot, authority, Vec::new()))
    })
}

pub fn cmd_managed(command: ManagedCommands) -> ! {
    match command {
        ManagedCommands::Require {
            id,
            checks,
            reason,
            json,
        } => cmd_require(id, checks, reason, json),
        ManagedCommands::Correct { id, reason, json } => cmd_correct(id, reason, json),
        ManagedCommands::Release {
            id,
            reason,
            isolated_checkout,
            json,
        } => cmd_release(id, reason, isolated_checkout, json),
        ManagedCommands::History { id, json } => cmd_history(id, json),
        ManagedCommands::Recover { id, json } => cmd_recover(id, json),
        ManagedCommands::Doctor { probe, json } => cmd_doctor(probe, json),
    }
}

fn cmd_require(id: String, checks: Vec<String>, reason: Option<String>, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    if issue.issue_type != IssueType::Item {
        fail(
            &format!("{} is a {}; only items carry managed closure", id, issue.issue_type),
            EXIT_USER_ERROR,
            json,
        );
    }
    let checks: Vec<String> = checks
        .into_iter()
        .map(|check| check.trim().to_string())
        .filter(|check| !check.is_empty())
        .collect();
    if checks.is_empty() {
        fail("--check names must not be empty", EXIT_USER_ERROR, json);
    }
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    preview_coordination(&session, &issue, &grants, "managed require", json);
    let actor = session.id().to_string();
    let reason_text = reason.clone();
    // `require` may create the record, so it cannot use coordinator_mutation
    // (which demands an existing one); the same locked shape is inlined.
    let result = board.with_locked_issue(&id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
        let grants = store.load_grants()?;
        let authority = revalidate_authority(&session, current, &grants, "managed require")?;
        let grant_label = authority
            .grant
            .clone()
            .unwrap_or_else(|| "operator".to_string());
        let mut managed = store.load_managed()?;
        let record = managed.items.entry(id.clone()).or_insert_with(|| ManagedRecord {
            id: id.clone(),
            attempt: 1,
            required: Vec::new(),
            grant: grant_label.clone(),
            managed_at: now_label(),
            managed_by: actor.clone(),
            target: None,
            submission: None,
            acceptances: Vec::new(),
            releases: Vec::new(),
            history: Vec::new(),
        });
        if record.release_interrupted(current) {
            return Err(format!(
                "{} has an interrupted release; complete it with `manna managed release {} --reason <text>` first",
                id, id
            ));
        }
        if let Some(refusal) = store.incomplete_transaction(&id)? {
            return Err(refusal);
        }
        for check in &checks {
            if !record.required.iter().any(|existing| existing == check) {
                record.required.push(check.clone());
            }
        }
        let snapshot = record.clone();
        let event = lifecycle_event(
            "require",
            &id,
            &session,
            &authority.level,
            Some(snapshot.attempt),
            reason_text.as_deref(),
            None,
            Some(serde_json::json!({"required": snapshot.required})),
        );
        let intent = intent_for(&session, &id, event, Some(snapshot.clone()), None);
        store
            .run_transaction(intent.clone())
            .map_err(|error| transaction_failed(&intent, error))?;
        Ok((snapshot, authority, Vec::new()))
    });
    let (record, authority, warnings) = match result {
        Ok(value) => value,
        Err(error) => rejected(error, json),
    };
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
            warnings,
        },
        json,
    )
}

/// `manna submit <id> --report <file|-> [--revision <ref>]`: the claim-holder
/// records its result for the current attempt. The item stays in_progress;
/// submission is not acceptance, and every submission is a new one: an
/// acceptance given on an earlier report does not carry to this one.
pub fn cmd_submit(id: String, report: PathBuf, revision: Option<String>, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let text = if report.as_os_str() == "-" {
        let mut buffer = String::new();
        use std::io::Read;
        if let Err(error) = std::io::stdin().read_to_string(&mut buffer) {
            fail(&format!("cannot read report from stdin: {}", error), EXIT_USER_ERROR, json);
        }
        buffer
    } else {
        match std::fs::read_to_string(&report) {
            Ok(text) => text,
            Err(error) => fail(
                &format!("cannot read report {}: {}", report.display(), error),
                EXIT_USER_ERROR,
                json,
            ),
        }
    };
    if text.trim().is_empty() {
        fail("the report is empty; a submission carries what was done, the receipts, and what was left", EXIT_USER_ERROR, json);
    }
    let resolved_revision = match revision.as_deref() {
        Some(reference) => match git_resolve(reference) {
            Ok(resolved) => Some(resolved.sha),
            Err(error) => fail(&format!("--revision {}: {}", reference, error), EXIT_USER_ERROR, json),
        },
        None => None,
    };
    let actor = session.id().to_string();
    let result = board.with_locked_issue(&id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
        // The submitter must hold the live claim: a superseded worker whose
        // claim was released cannot submit over the replacement.
        if current.claimed_by.is_none() {
            return Err(format!(
                "{} is not claimed; submit from the session that holds the claim",
                id
            ));
        }
        current.require_owner(&session)?;
        let mut managed = store.load_managed()?;
        let record = managed
            .items
            .get_mut(&id)
            .ok_or_else(|| format!("{} is not a managed item (coordinator runs `manna managed require {} --check <name>`)", id, id))?;
        if record.release_interrupted(current) {
            return Err(format!(
                "{} has an interrupted release; a coordinator completes it before a submission can land",
                id
            ));
        }
        if let Some(refusal) = store.incomplete_transaction(&id)? {
            return Err(refusal);
        }
        let at = now_label();
        let submission = Submission {
            id: submission_id(record.attempt, &actor, &at, &text),
            attempt: record.attempt,
            by: actor.clone(),
            at,
            revision: resolved_revision.clone(),
            report: text.clone(),
            status: "submitted".to_string(),
            correction: None,
        };
        let superseded = record.submission.replace(submission.clone());
        if let Some(previous) = superseded.clone() {
            record.history.push(previous);
        }
        let snapshot = record.clone();
        let authority = if session.is_operator() { "operator" } else { "owner" };
        let event = lifecycle_event(
            "submit",
            &id,
            &session,
            authority,
            Some(snapshot.attempt),
            None,
            resolved_revision.as_deref(),
            Some(serde_json::json!({
                "submission": submission.id,
                "supersedes": superseded.map(|s| s.key()),
                "report_chars": text.chars().count(),
            })),
        );
        let intent = intent_for(&session, &id, event, Some(snapshot.clone()), None);
        store
            .run_transaction(intent.clone())
            .map_err(|error| transaction_failed(&intent, error))?;
        Ok((snapshot, Vec::<String>::new()))
    });
    let (record, warnings) = match result {
        Ok(value) => value,
        Err(error) => rejected(error, json),
    };
    let grants = load_grants_or_fail(&store, json);
    let authority = Authority::resolve(&session, &issue, &grants);
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
            warnings,
        },
        json,
    )
}

fn cmd_correct(id: String, reason: String, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    preview_coordination(&session, &issue, &grants, "managed correct", json);
    if reason.trim().is_empty() {
        fail("--reason must not be empty", EXIT_USER_ERROR, json);
    }
    let actor = session.id().to_string();
    let reason_text = reason.trim().to_string();
    let result = coordinator_mutation(&board, &store, &id, &session, "managed correct", |_, record, authority| {
        let submission = record
            .current_submission()
            .cloned()
            .ok_or_else(|| format!("no submission for attempt {} to correct", record.attempt))?;
        let key = submission.key();
        let mut updated = submission;
        updated.status = "correction_requested".to_string();
        updated.correction = Some(Correction {
            by: actor.clone(),
            at: now_label(),
            reason: reason_text.clone(),
        });
        record.submission = Some(updated);
        Ok(lifecycle_event(
            "correct",
            &id,
            &session,
            &authority.level,
            Some(record.attempt),
            Some(&reason_text),
            None,
            Some(serde_json::json!({"submission": key})),
        ))
    });
    let (record, authority, warnings) = match result {
        Ok(value) => value,
        Err(error) => rejected(error, json),
    };
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
            warnings,
        },
        json,
    )
}

/// `manna accept <id> --check <name> --target <ref> --evidence <text>`: an
/// authorized coordinator records one required check as accepted for the
/// exact current submission at an explicitly pinned integration target.
pub fn cmd_accept(
    id: String,
    check: String,
    target: String,
    evidence: String,
    expected_submission: String,
    expected_attempt: u32,
    repin: bool,
    json: bool,
) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    preview_coordination(&session, &issue, &grants, "accept", json);
    if evidence.trim().is_empty() {
        fail("--evidence must name what was verified (a merge, a deploy id, a test run)", EXIT_USER_ERROR, json);
    }
    let resolved = match git_resolve(&target) {
        Ok(resolved) => resolved,
        Err(error) => fail(
            &format!("integration target {} is unavailable: {}. Nothing was accepted", target, error),
            EXIT_USER_ERROR,
            json,
        ),
    };
    let expected_submission = expected_submission.trim().to_string();
    if expected_submission.is_empty() {
        fail("--submission must name the submission you reviewed (`manna assess` prints submission_key)", EXIT_USER_ERROR, json);
    }
    let actor = session.id().to_string();
    let check_name = check.trim().to_string();
    let evidence_text = evidence.trim().to_string();
    let result = coordinator_mutation(&board, &store, &id, &session, "accept", |_, record, authority| {
        // The verdict is for what the coordinator looked at. Under the lock
        // the record is reloaded: a submission or attempt that moved since
        // that look is a different artifact, and the verdict does not apply.
        if record.attempt != expected_attempt {
            return Err(format!(
                "you reviewed attempt {}, but {} is now on attempt {}; nothing was accepted. Re-run `manna assess {}` and review the current submission",
                expected_attempt, id, record.attempt, id
            ));
        }
        let current_key = record.current_submission().map(Submission::key);
        if current_key.as_deref() != Some(expected_submission.as_str()) {
            return Err(format!(
                "you reviewed submission {}, but the current submission of {} is {}; nothing was accepted. Review the current one and accept it by its id",
                expected_submission,
                id,
                current_key.as_deref().unwrap_or("none")
            ));
        }
        if !record.required.iter().any(|required| required == &check_name) {
            return Err(format!(
                "`{}` is not a required check on {} (required: {})",
                check_name,
                id,
                record.required.join(", ")
            ));
        }
        let submission = record.current_submission().ok_or_else(|| {
            format!(
                "no submission for attempt {}; acceptance records a verdict on a submitted result, not on an empty attempt",
                record.attempt
            )
        })?;
        if submission.status != "submitted" {
            return Err(format!(
                "the current submission {} is {}; a result that was sent back is not accepted until it is resubmitted",
                submission.key(),
                submission.status
            ));
        }
        let submission_key = submission.key();
        match record.target.as_ref() {
            Some(pinned) if pinned.sha != resolved.sha && !repin => {
                return Err(format!(
                    "integration target is pinned to {} ({} = {}); {} resolves to {}. Pass --repin to move it, which leaves earlier acceptances at the old target not counting",
                    pinned.sha, pinned.reference, pinned.kind, target, resolved.sha
                ));
            }
            Some(pinned) if pinned.sha == resolved.sha => {}
            _ => {
                record.target = Some(PinnedTarget {
                    reference: target.clone(),
                    sha: resolved.sha.clone(),
                    kind: resolved.kind.clone(),
                    pinned_at: now_label(),
                    pinned_by: actor.clone(),
                });
            }
        }
        record.acceptances.push(Acceptance {
            check: check_name.clone(),
            attempt: record.attempt,
            submission: submission_key.clone(),
            target_sha: resolved.sha.clone(),
            by: actor.clone(),
            authority: authority.level.clone(),
            at: now_label(),
            evidence: evidence_text.clone(),
        });
        Ok(lifecycle_event(
            "accept",
            &id,
            &session,
            &authority.level,
            Some(record.attempt),
            None,
            Some(&evidence_text),
            Some(serde_json::json!({
                "check": check_name,
                "submission": submission_key,
                "target": target,
                "target_sha": resolved.sha,
                "target_kind": resolved.kind,
            })),
        ))
    });
    let (record, authority, warnings) = match result {
        Ok(value) => value,
        Err(error) => rejected(error, json),
    };
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
            warnings,
        },
        json,
    )
}

// ----------------------------------------------------------------------------
// liveness, from its owning source
// ----------------------------------------------------------------------------

#[derive(Serialize, Clone)]
pub struct Liveness {
    /// coord's classification (`active`, `idle`, `stale`, `dead`, `stopped`,
    /// `unclaimed`) or `unknown`.
    pub status: String,
    pub source: String,
    pub observed_at: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub matched_agent: Option<String>,
    /// True only for `dead` (process verified gone or tombstoned) and
    /// `stopped` (the session retired itself). `active` is a current lease;
    /// `idle`/`stale` are an aged lease, which says nothing about death.
    pub verified_gone: bool,
    pub note: String,
}

fn hex_tail(value: &str) -> String {
    let lower = value.to_ascii_lowercase();
    let tail = lower.rsplit('-').next().unwrap_or(&lower);
    if !tail.is_empty() && tail.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        tail.to_string()
    } else {
        lower
    }
}

/// Match a claim label to a coord peer the way `manna state` does: exact id,
/// the compact `session-` form, or a shared hex tail (coord keeps twelve
/// hex characters of a session id, manna's label keeps sixteen).
fn coord_peer_for_owner(statuses: &std::collections::HashMap<String, String>, owner: &str) -> Option<(String, String)> {
    if let Some(status) = statuses.get(owner) {
        return Some((owner.to_string(), status.clone()));
    }
    let compact = owner
        .chars()
        .filter(|character| character.is_ascii_alphanumeric())
        .flat_map(char::to_lowercase)
        .take(16)
        .collect::<String>();
    if !compact.is_empty() {
        // coord keeps twelve characters of an explicit session anchor;
        // manna's compact label keeps sixteen. Try both spellings.
        for width in [16usize, 12usize] {
            let label = format!("session-{}", compact.chars().take(width).collect::<String>());
            if let Some(status) = statuses.get(&label) {
                return Some((label, status.clone()));
            }
        }
    }
    let wanted = hex_tail(owner);
    if wanted.is_empty() {
        return None;
    }
    statuses.iter().find_map(|(agent_id, status)| {
        let have = hex_tail(agent_id);
        (!have.is_empty() && (wanted.starts_with(&have) || have.starts_with(&wanted)))
            .then(|| (agent_id.clone(), status.clone()))
    })
}

pub fn liveness_for(owner: Option<&str>) -> Liveness {
    let observed_at = now_label();
    let Some(owner) = owner else {
        return Liveness {
            status: "unclaimed".to_string(),
            source: "board row".to_string(),
            observed_at,
            matched_agent: None,
            verified_gone: false,
            note: "no claim on the row".to_string(),
        };
    };
    match coord_peer_statuses_all() {
        Ok(statuses) => match coord_peer_for_owner(&statuses, owner) {
            Some((agent, status)) => {
                let verified_gone = status == "dead" || status == "stopped";
                let note = match status.as_str() {
                    "dead" => "coord verified the process gone or tombstoned the session",
                    "stopped" => "the session retired itself through coord stop",
                    "active" => "a current presence lease; the session is live",
                    "idle" | "stale" => "an aged lease: says nothing about whether the process is alive",
                    _ => "coord has no verdict",
                }
                .to_string();
                Liveness {
                    status,
                    source: "agent-do coord peers --json".to_string(),
                    observed_at,
                    matched_agent: Some(agent),
                    verified_gone,
                    note,
                }
            }
            None => Liveness {
                status: "unknown".to_string(),
                source: "agent-do coord peers --json".to_string(),
                observed_at,
                matched_agent: None,
                verified_gone: false,
                note: "coord lists no peer for this claim label".to_string(),
            },
        },
        Err(error) => Liveness {
            status: "unknown".to_string(),
            source: "agent-do coord peers --json".to_string(),
            observed_at,
            matched_agent: None,
            verified_gone: false,
            note: format!("coord unavailable: {}", error),
        },
    }
}

/// A replacement checkout is accepted only as a real, separate git working
/// tree: it exists, git answers inside it, and its toplevel is not this
/// checkout's. A name alone proves nothing.
fn validate_isolated_checkout(path: &str) -> Result<String, String> {
    let path = path.trim();
    if path.is_empty() {
        return Err("--isolated-checkout needs a path".to_string());
    }
    let candidate = Path::new(path);
    if !candidate.is_dir() {
        return Err(format!("{} is not an existing directory", path));
    }
    let toplevel = std::process::Command::new("git")
        .arg("-C")
        .arg(candidate)
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .map_err(|error| format!("git unavailable: {}", error))?;
    if !toplevel.status.success() {
        return Err(format!("{} is not inside a git working tree", path));
    }
    let theirs = String::from_utf8_lossy(&toplevel.stdout).trim().to_string();
    let theirs_canonical = std::fs::canonicalize(&theirs).unwrap_or_else(|_| PathBuf::from(&theirs));
    let ours = git_output(&["rev-parse", "--show-toplevel"])?;
    let ours_canonical = std::fs::canonicalize(&ours).unwrap_or_else(|_| PathBuf::from(&ours));
    if theirs_canonical == ours_canonical {
        return Err(format!(
            "{} resolves to this checkout ({}); isolation means a different working tree",
            path,
            ours_canonical.display()
        ));
    }
    Ok(theirs_canonical.display().to_string())
}

fn cmd_release(id: String, reason: String, isolated_checkout: Option<String>, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    preview_coordination(&session, &issue, &grants, "managed release", json);
    if reason.trim().is_empty() {
        fail("--reason must not be empty", EXIT_USER_ERROR, json);
    }
    let inspected = store
        .record_for(&id)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json))
        .unwrap_or_else(|| fail(&format!("{} is not a managed item", id), EXIT_USER_ERROR, json));
    let resuming = inspected.release_interrupted(&issue);

    // Liveness from coord, the one source that verifies processes. Only a
    // verified death or a self-retirement, or a validated separate working
    // tree, releases a held claim; an aged lease or no verdict never seats a
    // second writer in the same files.
    let worker = issue.claimed_by.clone();
    let liveness = liveness_for(worker.as_deref());
    let isolation_toplevel = match isolated_checkout.as_deref() {
        Some(path) => Some(validate_isolated_checkout(path).unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json))),
        None => None,
    };
    let basis = if resuming {
        "resume"
    } else if worker.is_none() {
        "unclaimed"
    } else if liveness.verified_gone {
        "coord_dead"
    } else if isolation_toplevel.is_some() {
        "isolated_checkout"
    } else {
        fail(
            &format!(
                "worker {} liveness is `{}` ({}); that is not a verified stop. Release needs coord to report the worker dead or stopped (`agent-do coord stop` in its session, or a verified-gone process), or --isolated-checkout <path> naming a separate git working tree for the replacement",
                worker.as_deref().unwrap_or("?"),
                liveness.status,
                liveness.note
            ),
            EXIT_NEEDS_AUTHORIZATION,
            json,
        );
    };

    let actor = session.id().to_string();
    let expected_worker = worker.clone();
    let expected_attempt = inspected.attempt;
    let reason_text = reason.trim().to_string();
    let liveness_label = liveness.status.clone();
    let isolation = isolated_checkout.clone();
    let isolation_top = isolation_toplevel.clone();
    let before_store = managed_store();
    let after_store = managed_store();
    let before_session = session.clone();
    let before_id = id.clone();
    let after_id = id.clone();
    let result = board.release_claim_with(
        &id,
        move |current, _| {
            if current.status == IssueStatus::Done {
                return Err(format!("{} is already done", before_id));
            }
            if current.claimed_by != expected_worker {
                return Err(format!(
                    "claim changed after inspection (expected {:?}, found {:?}); nothing was released",
                    expected_worker, current.claimed_by
                ));
            }
            let grants = before_store.load_grants()?;
            let authority = revalidate_authority(&before_session, current, &grants, "managed release")?;
            let mut managed = before_store.load_managed()?;
            let record = managed
                .items
                .get_mut(&before_id)
                .ok_or_else(|| format!("{} is not a managed item", before_id))?;
            if let Some(refusal) = before_store.incomplete_transaction(&before_id)? {
                return Err(refusal);
            }
            if resuming {
                if !record.release_interrupted(current) {
                    return Err("the interrupted release completed meanwhile; nothing to resume".to_string());
                }
                let event = lifecycle_event(
                    "release_resume",
                    &before_id,
                    &before_session,
                    &authority.level,
                    Some(record.attempt),
                    Some(&reason_text),
                    None,
                    Some(serde_json::json!({"worker": current.claimed_by})),
                );
                let intent = intent_for(&before_session, &before_id, event, None, None);
                return before_store
                    .run_transaction(intent.clone())
                    .map_err(|error| transaction_failed(&intent, error));
            }
            if record.attempt != expected_attempt {
                return Err(format!(
                    "attempt moved from {} to {} after inspection; nothing was released",
                    expected_attempt, record.attempt
                ));
            }
            let released_attempt = record.attempt;
            record.releases.push(Release {
                attempt: released_attempt,
                by: actor.clone(),
                at: now_label(),
                reason: reason_text.clone(),
                worker: expected_worker.clone(),
                worker_liveness: liveness_label.clone(),
                basis: basis.to_string(),
                isolation: isolation.clone(),
                isolation_toplevel: isolation_top.clone(),
                claim_release: if expected_worker.is_some() { "pending" } else { "released" }.to_string(),
            });
            if let Some(previous) = record.submission.take() {
                record.history.push(previous);
            }
            record.attempt = released_attempt + 1;
            let next = record.attempt;
            let pending_record = record.clone();
            let event = lifecycle_event(
                "release",
                &before_id,
                &before_session,
                &authority.level,
                Some(next),
                Some(&reason_text),
                None,
                Some(serde_json::json!({
                    "released_attempt": released_attempt,
                    "worker": expected_worker,
                    "worker_liveness": liveness_label,
                    "basis": basis,
                    "isolation": isolation,
                    "isolation_toplevel": isolation_top,
                })),
            );
            // Pending phase first, as one transaction (intent, sidecar,
            // audit): once the intent is durable, a death anywhere below
            // leaves a visible, resumable state, never a silent one.
            let intent = intent_for(&before_session, &before_id, event, Some(pending_record), None);
            before_store
                .run_transaction(intent.clone())
                .map_err(|error| transaction_failed(&intent, error))?;
            fault("after_release_pending");
            Ok(())
        },
        move |_row| {
            let mut managed = after_store.load_managed()?;
            if let Some(record) = managed.items.get_mut(&after_id) {
                if let Some(release) = record
                    .releases
                    .iter_mut()
                    .rev()
                    .find(|release| release.claim_release == "pending")
                {
                    release.claim_release = "released".to_string();
                }
            }
            after_store.save_managed(&managed)
        },
    );
    let released_issue = match result {
        Ok(issue) => issue,
        Err(error) => rejected(error, json),
    };
    let record = store
        .record_for(&id)
        .ok()
        .flatten()
        .unwrap_or(inspected);
    let grants = load_grants_or_fail(&store, json);
    let authority = Authority::resolve(&session, &released_issue, &grants);
    emit(
        ManagedData {
            issue: IssueData {
                age: (&released_issue).into(),
                issue: released_issue,
            },
            managed: record,
            authority,
            warnings: Vec::new(),
        },
        json,
    )
}

fn cmd_history(id: String, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let _ = find_issue(&issues, &id);
    let store = managed_store();
    let managed = store
        .record_for(&id)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    let events = store
        .events_for(&id)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    emit(HistoryData { managed, events }, json)
}

// ----------------------------------------------------------------------------
// git evidence
// ----------------------------------------------------------------------------

pub struct ResolvedRef {
    pub sha: String,
    pub kind: String,
    pub is_head: bool,
}

fn git_output(args: &[&str]) -> Result<String, String> {
    let out = std::process::Command::new("git")
        .args(args)
        .stderr(std::process::Stdio::piped())
        .output()
        .map_err(|error| format!("git unavailable: {}", error))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
        return Err(if stderr.is_empty() {
            format!("git {} failed", args.join(" "))
        } else {
            stderr
        });
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn git_ref_exists(full: &str) -> bool {
    git_output(&["show-ref", "--verify", "--quiet", full]).is_ok()
}

/// Resolve a reference to a commit and say what kind of reference it was,
/// so the record distinguishes this checkout's HEAD from a local branch,
/// a remote-tracking ref, a tag, or a bare commit. No fetch, no checkout.
pub fn git_resolve(reference: &str) -> Result<ResolvedRef, String> {
    let reference = reference.trim();
    if reference.is_empty() {
        return Err("empty reference".to_string());
    }
    let sha = git_output(&["rev-parse", "--verify", &format!("{}^{{commit}}", reference)])
        .map_err(|error| format!("does not resolve to a commit in this repository ({})", error))?;
    let head = git_output(&["rev-parse", "--verify", "HEAD^{commit}"]).ok();
    let kind = if reference == "HEAD" {
        "head"
    } else if git_ref_exists(&format!("refs/heads/{}", reference)) {
        "local_branch"
    } else if git_ref_exists(&format!("refs/remotes/{}", reference)) {
        "remote_tracking"
    } else if git_ref_exists(&format!("refs/tags/{}", reference)) {
        "tag"
    } else if sha.starts_with(reference) {
        "commit"
    } else {
        "ref"
    };
    Ok(ResolvedRef {
        is_head: head.as_deref() == Some(sha.as_str()),
        sha,
        kind: kind.to_string(),
    })
}

#[derive(Serialize, Clone)]
pub struct TrailerCommit {
    pub sha: String,
    pub subject: String,
    pub touches_source: bool,
    /// `in_target`, `patch_equivalent`, or `elsewhere`.
    pub relation: String,
}

/// Every commit on any ref carrying this item's trailer, classified against
/// the target. A trailer is a receipt that work was committed; it is never
/// acceptance, and a patch-equivalent match is a hint for the coordinator,
/// never proof that the integration branch holds the work.
pub fn trailer_commits_for(id: &str, target_sha: Option<&str>) -> Result<Vec<TrailerCommit>, String> {
    let listing = git_output(&[
        "log",
        "--all",
        "--format=%H%x1f%s",
        &format!("--grep=^Manna: {}$", id),
    ])?;
    let mut commits = Vec::new();
    for line in listing.lines() {
        let mut parts = line.splitn(2, '\u{1f}');
        let sha = parts.next().unwrap_or("").trim().to_string();
        if sha.is_empty() {
            continue;
        }
        let subject = parts.next().unwrap_or("").trim().to_string();
        let body = git_output(&["show", "-s", "--format=%B", &sha]).unwrap_or_default();
        if !manna_trailer_ids(&body).iter().any(|found| found == id) {
            continue;
        }
        let relation = match target_sha {
            None => "unclassified".to_string(),
            Some(target) => {
                if git_output(&["merge-base", "--is-ancestor", &sha, target]).is_ok() {
                    "in_target".to_string()
                } else if patch_equivalent(&sha, target) {
                    "patch_equivalent".to_string()
                } else {
                    "elsewhere".to_string()
                }
            }
        };
        commits.push(TrailerCommit {
            touches_source: commit_touches_source(&sha),
            sha,
            subject,
            relation,
        });
    }
    Ok(commits)
}

fn patch_equivalent(sha: &str, target: &str) -> bool {
    let parent = format!("{}^", sha);
    if git_output(&["rev-parse", "--verify", &format!("{}^{{commit}}", parent)]).is_err() {
        return false;
    }
    match git_output(&["cherry", target, sha, &parent]) {
        Ok(listing) => listing.lines().any(|line| line.starts_with("- ")),
        Err(_) => false,
    }
}

// ----------------------------------------------------------------------------
// assess
// ----------------------------------------------------------------------------

#[derive(Serialize)]
pub struct TargetReport {
    pub requested: Option<String>,
    pub sha: Option<String>,
    pub kind: Option<String>,
    pub is_current_head: Option<bool>,
    pub current_head: Option<String>,
    /// What was pinned at acceptance time: a recorded fact about then.
    pub pinned: Option<PinnedTarget>,
    /// Whether the pinned commit still exists here, observed now.
    pub pinned_still_resolves: Option<bool>,
    /// Where the pinned reference name points now, observed now; `moved`
    /// says it no longer names the pinned commit.
    pub pinned_reference_now: Option<String>,
    pub pinned_reference_moved: Option<bool>,
    pub matches_pinned: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Serialize)]
pub struct DeployedReport {
    pub sha: Option<String>,
    pub asserted_by: String,
}

/// Where each section of the assessment comes from and when it was read, so
/// a reader never mistakes a recorded claim for a present observation.
#[derive(Serialize)]
pub struct Observations {
    pub git: serde_json::Value,
    pub coord: serde_json::Value,
    pub recorded: serde_json::Value,
}

#[derive(Serialize)]
pub struct Assessment {
    pub id: String,
    pub title: String,
    pub status: String,
    pub claimed_by: Option<String>,
    pub claimant: Liveness,
    pub managed: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub record: Option<ManagedRecord>,
    pub attempt: Option<u32>,
    pub release_interrupted: bool,
    pub required_checks: Vec<String>,
    /// Acceptances that count now: same attempt, same target, and given on
    /// the exact current submission. Their `evidence` is what the coordinator
    /// recorded at the time, not something re-verified here.
    pub accepted_checks: Vec<Acceptance>,
    pub outstanding_checks: Vec<String>,
    pub submission_status: Option<String>,
    pub submission_key: Option<String>,
    /// Acceptances on this attempt that no longer count and why.
    pub superseded_acceptances: Vec<serde_json::Value>,
    pub authority: Authority,
    pub integration_target: TargetReport,
    pub deployed_revision: DeployedReport,
    pub trailer_commits: Vec<TrailerCommit>,
    pub evidence_note: &'static str,
    pub observations: Observations,
    /// Transactions whose state and audit writes did not both land; the
    /// item refuses every mutation until `managed recover` finishes them.
    pub incomplete_transactions: Vec<serde_json::Value>,
    pub closable: bool,
    pub blockers: Vec<String>,
    pub next_action: String,
    /// `assess:v2:...` only for a closable verdict; `blocked:v2:...`
    /// otherwise. `done --assessment` refuses a blocked token outright and
    /// recomputes a closable one's conditions under the lock.
    pub assessment: String,
}

pub fn assess(
    issue: &Issue,
    record: Option<&ManagedRecord>,
    session: &SessionIdentity,
    grants: &GrantFile,
    requested_target: Option<&str>,
    deployed: Option<&str>,
) -> Assessment {
    let authority = Authority::resolve(session, issue, grants);
    let claimant = liveness_for(issue.claimed_by.as_deref());
    let store = managed_store();
    let pending = store.pending_intents_affecting(&issue.id).unwrap_or_default();
    let git_observed_at = now_label();
    let current_head = git_output(&["rev-parse", "--verify", "HEAD^{commit}"]).ok();
    let pinned = record.and_then(|record| record.target.clone());
    let pinned_still_resolves = pinned
        .as_ref()
        .map(|pinned| git_output(&["rev-parse", "--verify", &format!("{}^{{commit}}", pinned.sha)]).is_ok());
    let pinned_reference_now = pinned
        .as_ref()
        .and_then(|pinned| git_resolve(&pinned.reference).ok().map(|r| r.sha));
    let pinned_reference_moved = match (&pinned, &pinned_reference_now) {
        (Some(pinned), Some(now)) => Some(&pinned.sha != now),
        (Some(_), None) => Some(true),
        _ => None,
    };
    let (requested_sha, requested_kind, is_head, target_error) = match requested_target {
        Some(reference) => match git_resolve(reference) {
            Ok(resolved) => (Some(resolved.sha), Some(resolved.kind), Some(resolved.is_head), None),
            Err(error) => (None, None, None, Some(error)),
        },
        None => (None, None, None, None),
    };
    let matches_pinned = match (&requested_sha, &pinned) {
        (Some(requested), Some(pinned)) => Some(requested == &pinned.sha),
        _ => None,
    };
    let classify_against = requested_sha
        .clone()
        .or_else(|| pinned.as_ref().map(|pinned| pinned.sha.clone()));
    let trailer_commits = trailer_commits_for(&issue.id, classify_against.as_deref()).unwrap_or_default();

    let mut blockers = Vec::new();
    let mut superseded = Vec::new();
    for intent in &pending {
        if intent.issue_id == BOARD_SCOPE {
            blockers.push(format!(
                "incomplete board transaction {} ({} by {} at {}): the grants are not the truth until the operator runs `manna managed recover board`",
                intent.txn,
                intent.action,
                intent.actor,
                intent.started_at.to_rfc3339()
            ));
        } else {
            blockers.push(format!(
                "incomplete transaction {} ({} by {} at {}); run `manna managed recover {}`",
                intent.txn,
                intent.action,
                intent.actor,
                intent.started_at.to_rfc3339(),
                issue.id
            ));
        }
    }
    let (attempt, required, accepted, outstanding, submission_status, submission_key, interrupted) = match record {
        Some(record) => {
            blockers.extend(closure_blockers(issue, record));
            if let Some(error) = target_error.as_ref() {
                blockers.push(format!(
                    "requested target {} is unavailable: {}",
                    requested_target.unwrap_or("?"),
                    error
                ));
            }
            if matches_pinned == Some(false) {
                blockers.push(format!(
                    "requested target {} resolves to {}, pinned target is {} ({})",
                    requested_target.unwrap_or("?"),
                    requested_sha.as_deref().unwrap_or("?"),
                    pinned.as_ref().map(|p| p.sha.as_str()).unwrap_or("?"),
                    pinned.as_ref().map(|p| p.reference.as_str()).unwrap_or("?")
                ));
            }
            if pinned_still_resolves == Some(false) {
                blockers.push(format!(
                    "pinned integration target {} no longer resolves in this repository",
                    pinned.as_ref().map(|p| p.sha.as_str()).unwrap_or("?")
                ));
            }
            let counted: Vec<Acceptance> = record.accepted_checks().into_iter().cloned().collect();
            let current_key = record.current_submission().map(Submission::key);
            for acceptance in record.acceptances.iter().filter(|a| a.attempt == record.attempt) {
                if counted.iter().any(|c| c == acceptance) {
                    continue;
                }
                let why = if current_key.as_deref() != Some(acceptance.submission.as_str()) {
                    if acceptance.submission.is_empty() {
                        "names no submission (recorded before acceptance was bound to one)"
                    } else {
                        "given on an earlier submission; the current one has not been accepted"
                    }
                } else {
                    "given at a different integration target than the pinned one"
                };
                superseded.push(serde_json::json!({
                    "check": acceptance.check,
                    "submission": acceptance.submission,
                    "target_sha": acceptance.target_sha,
                    "by": acceptance.by,
                    "at": acceptance.at,
                    "why": why,
                }));
            }
            (
                Some(record.attempt),
                record.required.clone(),
                counted,
                record.outstanding_checks(),
                record.current_submission().map(|s| s.status.clone()),
                current_key,
                record.release_interrupted(issue),
            )
        }
        None => {
            if issue.status == IssueStatus::Done {
                blockers.push(format!("{} is already done", issue.id));
            } else if issue.issue_type == IssueType::Dream {
                blockers.push("dreams close through conversion or their own close transition".to_string());
            } else {
                let evidence = trailer_commits.iter().filter(|c| c.touches_source).count();
                if evidence == 0 && !authority.operator && !authority.owner {
                    blockers.push("unmanaged item: closing needs the claim-holder's proof, the operator, or a source-touching trailer commit".to_string());
                }
            }
            (None, Vec::new(), Vec::new(), Vec::new(), None, None, false)
        }
    };
    let closable = blockers.is_empty();
    let conditions = AssessmentConditions {
        closable,
        blockers: blockers.clone(),
        requested_sha: requested_sha.clone(),
        pinned_reference_now: pinned_reference_now.clone(),
    };
    let next_action = if closable {
        match record {
            Some(_) if authority.coordinates() || authority.owner => {
                format!("agent-do manna done {} --assessment <assessment>", issue.id)
            }
            Some(_) => format!(
                "a coordinator with a grant over {} (or the operator) runs `agent-do manna done {}`",
                issue.id, issue.id
            ),
            None => format!("agent-do manna done {}", issue.id),
        }
    } else if pending.iter().any(|intent| intent.issue_id == BOARD_SCOPE) {
        "operator: agent-do manna managed recover board".to_string()
    } else if !pending.is_empty() {
        format!("agent-do manna managed recover {}", issue.id)
    } else if interrupted {
        format!("coordinator: agent-do manna managed release {} --reason \"complete the interrupted release\"", issue.id)
    } else if let Some(record) = record {
        match record.current_submission() {
            None => format!("worker: agent-do manna submit {} --report <file>", issue.id),
            Some(submission) if submission.status == "correction_requested" => {
                format!("worker: address the correction, then agent-do manna submit {} --report <file>", issue.id)
            }
            Some(_) if !outstanding.is_empty() && authority.coordinates() => format!(
                "agent-do manna accept {} --check {} --target <ref> --evidence \"<what was verified>\"",
                issue.id, outstanding[0]
            ),
            Some(_) if !outstanding.is_empty() => format!(
                "coordinator ({}) records acceptance for: {}",
                record.grant,
                outstanding.join(", ")
            ),
            Some(_) => "resolve the blockers above, then re-run assess".to_string(),
        }
    } else {
        "resolve the blockers above, then re-run assess".to_string()
    };
    Assessment {
        id: issue.id.clone(),
        title: issue.title.clone(),
        status: issue.status.to_string(),
        claimed_by: issue.claimed_by.clone(),
        claimant,
        managed: record.is_some(),
        record: record.cloned(),
        attempt,
        release_interrupted: interrupted,
        required_checks: required,
        accepted_checks: accepted,
        outstanding_checks: outstanding,
        submission_status,
        submission_key,
        superseded_acceptances: superseded,
        authority,
        integration_target: TargetReport {
            requested: requested_target.map(str::to_string),
            sha: requested_sha,
            kind: requested_kind,
            is_current_head: is_head,
            current_head: current_head.clone(),
            pinned,
            pinned_still_resolves,
            pinned_reference_now,
            pinned_reference_moved,
            matches_pinned,
            error: target_error,
        },
        deployed_revision: DeployedReport {
            sha: deployed.map(str::to_string),
            asserted_by: if deployed.is_some() {
                "caller (--deployed); not observed by manna".to_string()
            } else {
                "not asserted".to_string()
            },
        },
        trailer_commits,
        evidence_note: "trailer commits and patch-equivalent matches are receipts that work was committed; they are never acceptance of a managed item",
        observations: Observations {
            git: serde_json::json!({
                "observed_at": git_observed_at,
                "source": "git in this checkout (rev-parse, log --all, merge-base, cherry); no fetch, no checkout",
                "covers": ["integration_target.sha", "integration_target.current_head", "integration_target.pinned_still_resolves", "integration_target.pinned_reference_now", "trailer_commits"],
            }),
            coord: serde_json::json!({
                "observed_at": git_observed_at,
                "source": "agent-do coord peers --json",
                "covers": ["claimant"],
            }),
            recorded: serde_json::json!({
                "source": ".manna/managed.json and .manna/coordinators.json",
                "covers": ["record", "accepted_checks[].evidence", "integration_target.pinned", "submission_status"],
                "note": "recorded claims from the moment they were written; the git and coord sections are what was observed now",
            }),
        },
        incomplete_transactions: pending
            .iter()
            .map(|intent| serde_json::json!({"txn": intent.txn, "scope": intent.issue_id, "action": intent.action, "actor": intent.actor, "started_at": intent.started_at}))
            .collect(),
        closable,
        blockers,
        next_action,
        assessment: assessment_token(issue, record, &conditions),
    }
}

pub fn cmd_assess(id: String, target: Option<String>, deployed: Option<String>, json: bool) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    let record = store
        .record_for(&id)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    let report = assess(
        &issue,
        record.as_ref(),
        &session,
        &grants,
        target.as_deref(),
        deployed.as_deref(),
    );
    emit(report, json)
}

// ----------------------------------------------------------------------------
// done gate (called by cmd_done)
// ----------------------------------------------------------------------------

pub struct ManagedClose {
    pub authority: &'static str,
    pub warnings: Vec<String>,
    /// The row is done and its dependents released, but the close's audit
    /// transaction did not complete. The command fails (nonzero) naming the
    /// transaction; `manna managed recover <id>` finishes it.
    pub incomplete: Option<IncompleteClose>,
}

pub struct IncompleteClose {
    pub transaction: String,
    pub error: String,
}

/// Refuse or authorize a managed close. Returns `None` for unmanaged items.
/// The decisive checks run under the board lock with the row, the grants and
/// the sidecar re-read: authority, expected owner, attempt, every blocker,
/// and the assessment digest when one was handed in.
pub fn close_managed(
    board: &MannaStore,
    issue: &Issue,
    session: &SessionIdentity,
    expected_assessment: Option<&str>,
) -> Option<Result<(manna_core::store::CompletedIssue, ManagedClose), MannaError>> {
    let store = managed_store();
    let record = match store.record_for(&issue.id) {
        Ok(Some(record)) => record,
        Ok(None) => return None,
        Err(error) => return Some(Err(MannaError::MutationRejected(error))),
    };
    let grants = match store.load_grants() {
        Ok(grants) => grants,
        Err(error) => return Some(Err(MannaError::MutationRejected(error))),
    };
    let authority = Authority::resolve(session, issue, &grants);
    if !(authority.coordinates() || authority.owner) {
        return Some(Err(MannaError::MutationRejected(format!(
            "{} is a managed item: closing needs a coordinator grant held by this session, the operator, or the claim-holder's proof (level here: {}). Trailer commits do not close managed items; see `agent-do manna assess {}`",
            issue.id, authority.level, issue.id
        ))));
    }
    let blockers = closure_blockers(issue, &record);
    if !blockers.is_empty() {
        return Some(Err(MannaError::MutationRejected(format!(
            "{} cannot close: {}. See `agent-do manna assess {}`",
            issue.id,
            blockers.join("; "),
            issue.id
        ))));
    }
    // A handed-in assessment is checked for what it is before anything
    // else: a blocked verdict never authorizes, and only a current-format
    // closable one is recomputed under the lock.
    let token = match expected_assessment {
        Some(expected) => match parse_assessment_token(expected) {
            Ok(token) => Some(token),
            Err(reason) => return Some(Err(MannaError::MutationRejected(reason))),
        },
        None => None,
    };
    if let Some(reason) = store.incomplete_transaction(&issue.id).unwrap_or(None) {
        return Some(Err(MannaError::MutationRejected(reason)));
    }
    let id = issue.id.clone();
    let inner_id = id.clone();
    let expected_owner = issue.claimed_by.clone();
    let expected_attempt = record.attempt;
    let precondition_store = managed_store();
    let precondition_session = session.clone();
    let level_cell = std::cell::Cell::new("owner");
    let level_ref = &level_cell;
    let intent_cell: std::cell::RefCell<Option<Intent>> = std::cell::RefCell::new(None);
    let intent_ref = &intent_cell;
    let audit_store = managed_store();
    let audit_session = session.clone();
    let audit_id = id.clone();
    let audit_record = record.clone();
    let result = board.complete_issue_on_acceptance_with(
        &id,
        move |current, _| {
            if let Some(refusal) = precondition_store.incomplete_transaction(&inner_id)? {
                return Err(refusal);
            }
            let grants = precondition_store.load_grants()?;
            let authority = Authority::resolve(&precondition_session, current, &grants);
            let owner_now = current.claimed_by.is_some()
                && current.require_owner(&precondition_session).is_ok();
            if !(authority.coordinates() || owner_now) {
                return Err(format!(
                    "authority changed before the close (level now: {}); nothing was closed",
                    authority.level
                ));
            }
            level_ref.set(match authority.level.as_str() {
                "operator" => "operator",
                "coordinator" => "coordinator",
                _ => "owner",
            });
            if current.claimed_by != expected_owner {
                return Err(format!(
                    "claim changed before the close (expected {:?}, found {:?}); nothing was closed",
                    expected_owner, current.claimed_by
                ));
            }
            let live = precondition_store
                .record_for(&inner_id)?
                .ok_or_else(|| format!("{} lost its managed record between assessment and close", inner_id))?;
            if live.attempt != expected_attempt {
                return Err(format!(
                    "attempt moved from {} to {} before the close; nothing was closed",
                    expected_attempt, live.attempt
                ));
            }
            let blockers = closure_blockers(current, &live);
            if !blockers.is_empty() {
                return Err(format!(
                    "managed state changed before the close: {}",
                    blockers.join("; ")
                ));
            }
            if let Some(token) = token.as_ref() {
                // Recompute the conditions the closable verdict named. The
                // pinned reference must still point where it pointed; a
                // requested target must still resolve to the pinned commit.
                let pinned_now = live
                    .target
                    .as_ref()
                    .and_then(|pinned| git_resolve(&pinned.reference).ok().map(|r| r.sha));
                if token.pinned_reference_now != pinned_now {
                    return Err(format!(
                        "the assessment was taken when {} pointed at {}; it points at {} now. Re-run `manna assess` and act on the current state; nothing was closed",
                        live.target.as_ref().map(|t| t.reference.as_str()).unwrap_or("the integration reference"),
                        token.pinned_reference_now.as_deref().unwrap_or("nothing"),
                        pinned_now.as_deref().unwrap_or("nothing")
                    ));
                }
                if let Some(requested) = token.requested_sha.as_deref() {
                    let pinned_sha = live.target.as_ref().map(|t| t.sha.as_str());
                    if Some(requested) != pinned_sha {
                        return Err(format!(
                            "the assessment was taken against {}, which is not the pinned target {}; nothing was closed",
                            requested,
                            pinned_sha.unwrap_or("none")
                        ));
                    }
                    if git_output(&["rev-parse", "--verify", &format!("{}^{{commit}}", requested)]).is_err() {
                        return Err(format!("the assessed target {} no longer resolves; nothing was closed", requested));
                    }
                }
                let now = closable_hex(current, Some(&live), token);
                if now != token.hex {
                    return Err(
                        "stale assessment: the row or its acceptance state moved since the assessment; re-run `manna assess` and act on the current state. Nothing was closed".to_string(),
                    );
                }
            }
            // The close's audit line is a transaction too: its intent is
            // durable before the row changes, so a failed append after the
            // row is written leaves a recoverable record, never a silent gap.
            let event = lifecycle_event(
                "close",
                &audit_id,
                &audit_session,
                level_ref.get(),
                Some(audit_record.attempt),
                None,
                None,
                Some(serde_json::json!({
                    "accepted": audit_record.accepted_checks().iter().map(|a| a.check.clone()).collect::<Vec<_>>(),
                    "submission": audit_record.current_submission().map(Submission::key),
                    "target": audit_record.target.as_ref().map(|t| t.sha.clone()),
                })),
            );
            let intent = intent_for(&audit_session, &audit_id, event, None, None);
            let mut intents = precondition_store.load_intents()?;
            intents.intents.push(intent.clone());
            precondition_store.save_intents(&intents)?;
            *intent_ref.borrow_mut() = Some(intent);
            Ok(())
        },
        move |_completed| {
            let Some(intent) = intent_ref.borrow().clone() else {
                return Err("close transaction intent missing".to_string());
            };
            audit_store.apply_intent(&intent)?;
            audit_store.retire_intent(&intent.txn)
        },
    );
    match result {
        Ok((completed, audit_error)) => {
            let closed_id = completed.issue.id.clone();
            let transaction = intent_cell
                .borrow()
                .as_ref()
                .map(|intent| intent.txn.clone())
                .unwrap_or_default();
            Some(Ok((
                completed,
                ManagedClose {
                    authority: level_cell.get(),
                    warnings: Vec::new(),
                    incomplete: audit_error.map(|error| IncompleteClose {
                        error: format!(
                            "{} is done on the board, but close transaction {} did not complete: {}. The close is not clean until `manna managed recover {}` finishes it",
                            closed_id, transaction, error, closed_id
                        ),
                        transaction,
                    }),
                },
            )))
        }
        Err(error) => Some(Err(error)),
    }
}

/// `manna managed recover <id>`: finish every incomplete transaction for the
/// item. Allowed for the operator, a coordinator whose grant covers the
/// item, or the session that started the transaction (same label and
/// proof). Idempotent: an audit line already present is not duplicated.
fn cmd_recover(id: String, json: bool) -> ! {
    let board = open_board();
    let store = managed_store();
    let session = require_session_identity();
    if id == BOARD_SCOPE {
        recover_board(&board, &store, &session, json);
    }
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let pending = store
        .pending_intents_for(&id)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    let board_pending = store
        .incomplete_transaction(BOARD_SCOPE)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    if pending.is_empty() {
        emit(
            serde_json::json!({"id": id, "recovered": [], "note": "no incomplete transaction", "board": board_pending}),
            json,
        );
    }
    let grants = load_grants_or_fail(&store, json);
    let authority = Authority::resolve(&session, &issue, &grants);
    let started_it = pending
        .iter()
        .all(|intent| intent.actor == session.id() && intent.actor_proof == session.proof());
    if !(authority.coordinates() || started_it) {
        fail(
            &format!(
                "recovering {} needs the operator, a coordinator whose grant covers it, or the session that started the transaction (level here: {})",
                id, authority.level
            ),
            EXIT_NEEDS_AUTHORIZATION,
            json,
        );
    }
    // A coordinator's authority is read from the grants file, and while a
    // board transaction is pending that file is not the truth: only the
    // operator or the session that started this transaction may proceed.
    if let Some(refusal) = board_pending.filter(|_| !(session.is_operator() || started_it)) {
        fail(&refusal, EXIT_NEEDS_AUTHORIZATION, json);
    }
    let recovered = board.with_board_lock(|| store.recover(&id).map_err(MannaError::MutationRejected));
    let recovered = match recovered {
        Ok(recovered) => recovered,
        Err(error) => rejected(error, json),
    };
    let record = store.record_for(&id).ok().flatten();
    emit(
        serde_json::json!({
            "id": id,
            "recovered": recovered,
            "managed": record,
            "authority": authority,
        }),
        json,
    )
}

/// `manna managed recover board`: finish an incomplete grant or revocation.
/// Only the operator, or the session that started it (the operator by
/// construction), may: a coordinator's own authority is what the pending
/// transaction decides, so it cannot be the one to decide it.
fn recover_board(board: &MannaStore, store: &ManagedStore, session: &SessionIdentity, json: bool) -> ! {
    let pending = store
        .pending_intents_for(BOARD_SCOPE)
        .unwrap_or_else(|error| fail(&error, EXIT_USER_ERROR, json));
    if pending.is_empty() {
        emit(
            serde_json::json!({"id": BOARD_SCOPE, "recovered": [], "note": "no incomplete board transaction"}),
            json,
        );
    }
    let started_it = pending
        .iter()
        .all(|intent| intent.actor == session.id() && intent.actor_proof == session.proof());
    if !(session.is_operator() || started_it) {
        fail(
            "recovering a board transaction (a coordinator grant or revocation) needs the operator or the session that started it; a coordinator cannot finish the transaction that decides its own authority",
            EXIT_NEEDS_AUTHORIZATION,
            json,
        );
    }
    let recovered = board.with_board_lock(|| store.recover(BOARD_SCOPE).map_err(MannaError::MutationRejected));
    let recovered = match recovered {
        Ok(recovered) => recovered,
        Err(error) => rejected(error, json),
    };
    let grants = load_grants_or_fail(store, json);
    emit(
        serde_json::json!({
            "id": BOARD_SCOPE,
            "recovered": recovered,
            "grants": grants.grants,
        }),
        json,
    )
}

/// Reconcile and other repair paths ask this before touching a managed item.
pub fn managed_guard(id: &str) -> Option<String> {
    let store = managed_store();
    match store.record_for(id) {
        Ok(Some(record)) => Some(format!(
            "{} is a managed item (attempt {}, grant {}): its lifecycle belongs to the coordinator; use `agent-do manna assess {}`, `manna managed release`, or `manna done` with recorded acceptance",
            id, record.attempt, record.grant, id
        )),
        Ok(None) => None,
        Err(error) => Some(format!("{}: managed sidecar unreadable ({}); refusing to repair blind", id, error)),
    }
}

/// Record a lifecycle line for a claim on a managed item so the audit holds
/// the whole story.
pub fn note_claim(id: &str, session: &SessionIdentity) {
    let store = managed_store();
    if let Ok(Some(record)) = store.record_for(id) {
        let event = lifecycle_event("claim", id, session, "owner", Some(record.attempt), None, None, None);
        if let Some(warning) = audit_warning(&store, &event) {
            eprintln!("Warning: {}", warning);
        }
    }
}

/// A worker abandoning a managed claim ends its attempt in the same locked
/// transaction that releases the row: the sidecar's pending phase and the
/// audit line first, then the claim comes off, then the released marker.
/// Returns `None` for unmanaged items so the ordinary path runs.
pub fn abandon_managed(
    board: &MannaStore,
    id: &str,
    session: &SessionIdentity,
) -> Option<Result<Issue, MannaError>> {
    let store = managed_store();
    match store.record_for(id) {
        Ok(Some(_)) => {}
        Ok(None) => return None,
        Err(error) => return Some(Err(MannaError::MutationRejected(error))),
    }
    let actor = session.id().to_string();
    let before_store = managed_store();
    let after_store = managed_store();
    let before_session = session.clone();
    let before_id = id.to_string();
    let after_id = id.to_string();
    Some(board.release_claim_with(
        id,
        move |current, _| {
            if current.claimed_by.is_none() {
                return Err("Issue is not claimed".to_string());
            }
            current.require_owner(&before_session)?;
            if !matches!(current.status, IssueStatus::InProgress | IssueStatus::Blocked) {
                return Err(format!(
                    "Cannot release issue with status '{}', must be 'in_progress' or 'blocked'",
                    current.status
                ));
            }
            let mut managed = before_store.load_managed()?;
            let record = managed
                .items
                .get_mut(&before_id)
                .ok_or_else(|| format!("{} is not a managed item", before_id))?;
            if record.release_interrupted(current) {
                return Err(format!(
                    "{} has an interrupted release; a coordinator completes it first",
                    before_id
                ));
            }
            if let Some(refusal) = before_store.incomplete_transaction(&before_id)? {
                return Err(refusal);
            }
            let ended = record.attempt;
            record.releases.push(Release {
                attempt: ended,
                by: actor.clone(),
                at: now_label(),
                reason: "worker abandoned the claim".to_string(),
                worker: current.claimed_by.clone(),
                worker_liveness: "self".to_string(),
                basis: "abandon".to_string(),
                isolation: None,
                isolation_toplevel: None,
                claim_release: "pending".to_string(),
            });
            if let Some(previous) = record.submission.take() {
                record.history.push(previous);
            }
            record.attempt = ended + 1;
            let next = record.attempt;
            let pending_record = record.clone();
            let event = lifecycle_event(
                "abandon",
                &before_id,
                &before_session,
                "owner",
                Some(next),
                Some("worker abandoned the claim"),
                None,
                Some(serde_json::json!({"released_attempt": ended})),
            );
            let intent = intent_for(&before_session, &before_id, event, Some(pending_record), None);
            before_store
                .run_transaction(intent.clone())
                .map_err(|error| transaction_failed(&intent, error))?;
            fault("after_abandon_pending");
            Ok(())
        },
        move |_row| {
            let mut managed = after_store.load_managed()?;
            if let Some(record) = managed.items.get_mut(&after_id) {
                if let Some(release) = record
                    .releases
                    .iter_mut()
                    .rev()
                    .find(|release| release.claim_release == "pending")
                {
                    release.claim_release = "released".to_string();
                }
            }
            after_store.save_managed(&managed)
        },
    ))
}

// ----------------------------------------------------------------------------
// doctor: installed, registered, verified
// ----------------------------------------------------------------------------

#[derive(Serialize)]
struct DoctorData {
    /// `true` only when a probe verified the lifecycle end to end on this
    /// machine; `false` when something is missing or the probe failed;
    /// `null` when nothing was verified (no `--probe`).
    live: Option<bool>,
    commands: serde_json::Value,
    hooks: serde_json::Value,
    board: serde_json::Value,
    verified: serde_json::Value,
    verdict: String,
}

fn repo_root_from_exe() -> Option<PathBuf> {
    // tools/agent-manna/target/release/manna-core -> repo root
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.ancestors().nth(4).map(Path::to_path_buf))
        .filter(|root| root.join("agent-do").is_file())
}

fn coord_program() -> Option<PathBuf> {
    direct_coord_program(Path::new("agent-do")).or_else(|| {
        repo_root_from_exe()
            .map(|root| root.join("tools").join("agent-coord"))
            .filter(|candidate| candidate.is_file())
    })
}

fn cmd_doctor(probe: bool, json: bool) -> ! {
    let exe = std::env::current_exe()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|_| "unknown".to_string());

    // Commands: what the installed programs answer.
    let coord_path = coord_program();
    let (coord_ok, coord_detail) = match coord_path.as_ref() {
        Some(program) => match std::process::Command::new(program).arg("help").output() {
            Ok(out) => {
                let text = String::from_utf8_lossy(&out.stdout);
                let ack = text.contains("drop ack");
                let resolve = text.contains("drop resolve");
                let action = text.contains("--action");
                (
                    ack && resolve && action,
                    serde_json::json!({"program": program.display().to_string(), "drop_ack": ack, "drop_resolve": resolve, "drop_action": action}),
                )
            }
            Err(error) => (
                false,
                serde_json::json!({"program": program.display().to_string(), "error": error.to_string()}),
            ),
        },
        None => (false, serde_json::json!({"program": null, "error": "agent-coord not found beside agent-do or this binary"})),
    };
    let commands = serde_json::json!({
        "manna": {
            "path": exe,
            "version": env!("CARGO_PKG_VERSION"),
            "capabilities": [CAPABILITY],
            "note": "the wrapper picks target/release first, then target/debug, then PATH; this is the binary that answered",
        },
        "coord": coord_detail,
        "available": coord_ok,
    });

    // Hooks: what the Claude settings register. Registration is a fact about
    // a file, not proof that a hook fires or reads the right identity.
    let settings = std::env::var("HOME")
        .map(|home| PathBuf::from(home).join(".claude").join("settings.json"))
        .ok();
    let settings_text = settings
        .as_ref()
        .and_then(|path| std::fs::read_to_string(path).ok());
    let registered = |name: &str| settings_text.as_deref().is_some_and(|text| text.contains(name));
    let prompt_router = registered("agent-do-prompt-router.py");
    let session_start = registered("agent-do-session-start.sh");
    let hooks_registered = prompt_router && session_start;
    let hooks = serde_json::json!({
        "settings": settings.as_ref().map(|p| p.display().to_string()),
        "readable": settings_text.is_some(),
        "prompt_router_registered": prompt_router,
        "session_start_registered": session_start,
        "registered": hooks_registered,
        "note": "registration read from the settings file; whether a registered hook fires with the shell's identity is only known from a probe",
    });

    // Board: what this board holds.
    let store = managed_store();
    let board = serde_json::json!({
        "initialized": Path::new(".manna").is_dir(),
        "managed_items": store.load_managed().map(|file| file.items.len()).ok(),
        "live_grants": store.load_grants().map(|file| file.grants.iter().filter(|g| g.is_live()).count()).ok(),
        "sidecars_present": store.present_files().iter().map(|p| p.display().to_string()).collect::<Vec<_>>(),
    });

    // Verified: only a probe produces a verdict about behaviour.
    let (verified, probe_ok) = if probe {
        let outcome = run_probe(coord_path.as_deref());
        let ok = outcome.get("passed").and_then(|v| v.as_bool()).unwrap_or(false);
        (outcome, Some(ok))
    } else {
        (
            serde_json::json!({
                "ran": false,
                "note": "not verified: run `manna managed doctor --probe` to exercise the managed and drop lifecycles through the real binaries and hooks in a throwaway fixture",
            }),
            None,
        )
    };

    let live = probe_ok.map(|ok| ok && coord_ok && hooks_registered);
    let verdict = match live {
        Some(true) => "live: commands available, hooks registered, and the end-to-end probe passed on this machine".to_string(),
        Some(false) => {
            let mut missing = Vec::new();
            if !coord_ok {
                missing.push("agent-coord lacks drop ack/resolve/--action".to_string());
            }
            if !hooks_registered {
                missing.push("Claude hooks not registered in ~/.claude/settings.json".to_string());
            }
            if probe_ok == Some(false) {
                missing.push(format!(
                    "probe failed: {}",
                    verified.get("failed_step").and_then(|v| v.as_str()).unwrap_or("see verified.steps")
                ));
            }
            format!("not live: {}", missing.join("; "))
        }
        None => format!(
            "not verified: commands {}, hooks {}; end-to-end behaviour is unknown until `--probe` runs",
            if coord_ok { "available" } else { "incomplete" },
            if hooks_registered { "registered" } else { "not registered" }
        ),
    };
    emit(
        DoctorData {
            live,
            commands,
            hooks,
            board,
            verified,
            verdict,
        },
        json,
    )
}

/// Exercise the real binaries in a throwaway fixture: manna-core (this
/// executable) for the managed lifecycle, the installed agent-coord for the
/// drop lifecycle, and the Claude prompt-router hook for identity. Every step
/// is recorded with its command and verdict; the first failure stops it.

const PROBE_STRIP: [&str; 9] = [
    "CODEX_THREAD_ID",
    "CLAUDE_THREAD_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_AGENT_ID",
    "TMUX_PANE",
    "AGENT_DO_COORD_PID",
    "AGENT_DO_COORD_PID_START",
    "AGENT_DO_COORD_SESSION",
    "MANNA_OPERATOR",
];

struct Probe {
    root: PathBuf,
    steps: Vec<serde_json::Value>,
    failed_step: Option<String>,
}

impl Probe {
    /// Run one step; after the first failure every later step is skipped and
    /// returns `None`, so the report names exactly where the probe stopped.
    fn run(
        &mut self,
        label: &str,
        program: &Path,
        args: &[&str],
        env: &[(&str, String)],
        stdin: Option<&str>,
    ) -> Option<String> {
        if self.failed_step.is_some() {
            return None;
        }
        let mut command = std::process::Command::new(program);
        command.args(args).current_dir(&self.root);
        for key in PROBE_STRIP {
            command.env_remove(key);
        }
        command.env("MANNA_OPERATOR", "0");
        for (key, value) in env {
            command.env(key, value);
        }
        command.stdin(std::process::Stdio::piped());
        command.stdout(std::process::Stdio::piped());
        command.stderr(std::process::Stdio::piped());
        let output = match command.spawn().and_then(|mut child| {
            use std::io::Write;
            if let Some(mut handle) = child.stdin.take() {
                let _ = handle.write_all(stdin.unwrap_or("").as_bytes());
            }
            child.wait_with_output()
        }) {
            Ok(output) => output,
            Err(error) => {
                self.failed_step = Some(format!("{}: cannot run {}: {}", label, program.display(), error));
                self.steps.push(serde_json::json!({"step": label, "ok": false, "error": error.to_string()}));
                return None;
            }
        };
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let ok = output.status.success();
        self.steps.push(serde_json::json!({
            "step": label,
            "command": format!("{} {}", program.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(), args.join(" ")),
            "ok": ok,
            "exit": output.status.code(),
            "stderr": String::from_utf8_lossy(&output.stderr).trim().to_string(),
        }));
        if !ok {
            self.failed_step = Some(format!("{} (exit {:?})", label, output.status.code()));
            return None;
        }
        Some(stdout)
    }
}

fn run_probe(coord: Option<&Path>) -> serde_json::Value {

    let exe = match std::env::current_exe() {
        Ok(exe) => exe,
        Err(error) => {
            return serde_json::json!({"ran": true, "passed": false, "failed_step": format!("current_exe: {}", error), "steps": []});
        }
    };
    let root = std::env::temp_dir().join(format!("manna-doctor-probe-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    if let Err(error) = std::fs::create_dir_all(&root) {
        return serde_json::json!({"ran": true, "passed": false, "failed_step": format!("mkdir {}: {}", root.display(), error), "steps": []});
    }
    let home = root.join("home");
    let _ = std::fs::create_dir_all(&home);
    let worker_env = [
        ("MANNA_SESSION_ID", "probe-worker".to_string()),
        ("MANNA_SESSION_TOKEN", "probe-worker-token-00000000000000000000000000".to_string()),
        ("AGENT_DO_HOME", home.display().to_string()),
        ("HOME", home.display().to_string()),
        ("AGENT_DO_COORD_SESSION", "probe-worker".to_string()),
    ];
    let lead_env = [
        ("MANNA_SESSION_ID", "probe-lead".to_string()),
        ("MANNA_SESSION_TOKEN", "probe-lead-token-0000000000000000000000000000".to_string()),
        ("AGENT_DO_HOME", home.display().to_string()),
        ("HOME", home.display().to_string()),
        ("AGENT_DO_COORD_SESSION", "probe-lead".to_string()),
    ];
    let mut probe = Probe { root: root.clone(), steps: Vec::new(), failed_step: None };
    let git = Path::new("git");
    probe.run("git init", git, &["init", "-q", "-b", "main"], &worker_env, None);
    probe.run("git root commit", git, &["-c", "user.email=probe@manna", "-c", "user.name=probe", "commit", "-q", "--allow-empty", "-m", "root"], &worker_env, None);
    probe.run("manna init", &exe, &["init"], &worker_env, None);
    let created = probe.run("manna create", &exe, &["create", "Probe item", "doctor probe"], &worker_env, None);
    let item = created
        .as_deref()
        .and_then(|text| text.lines().find_map(|line| line.trim().strip_prefix("id: ").map(str::to_string)))
        .unwrap_or_default();
    probe.run("git add board", git, &["add", "-A"], &worker_env, None);
    probe.run("git commit board", git, &["-c", "user.email=probe@manna", "-c", "user.name=probe", "commit", "-q", "-m", "board"], &worker_env, None);

    // The grant is written directly: the probe has no operator terminal, and
    // the grant file format is this binary's own.
    if probe.failed_step.is_none() {
        let lead_identity = manna_core::issue::SessionIdentity::from_token("probe-lead", "probe-lead-token-0000000000000000000000000000");
        match lead_identity {
            Ok(identity) => {
                let probe_store = ManagedStore::new(&root);
                let granted_at = now_label();
                let grant = Grant {
                    id: grant_id("probe-lead", identity.proof(), &granted_at),
                    coordinator_id: "probe-lead".to_string(),
                    coordinator_proof: identity.proof().to_string(),
                    scope: GrantScope { items: vec![item.clone()], tracks: vec![] },
                    reason: "doctor probe".to_string(),
                    granted_at,
                    granted_by: "doctor-probe".to_string(),
                    revoked: None,
                };
                let written = probe_store
                    .load_grants()
                    .and_then(|mut grants| {
                        grants.grants.push(grant);
                        probe_store.save_grants(&grants)
                    });
                probe.steps.push(serde_json::json!({"step": "write grant", "ok": written.is_ok(), "error": written.as_ref().err()}));
                if written.is_err() {
                    probe.failed_step = Some("write grant".to_string());
                }
            }
            Err(error) => {
                probe.steps.push(serde_json::json!({"step": "lead identity", "ok": false, "error": error}));
                probe.failed_step = Some("lead identity".to_string());
            }
        }
    }
    probe.run("managed require", &exe, &["managed", "require", &item, "--check", "integration"], &lead_env, None);
    probe.run("worker claim", &exe, &["claim", &item], &worker_env, None);
    let submitted = probe.run("worker submit", &exe, &["submit", &item, "--report", "-", "--json"], &worker_env, Some("probe report\n"))
        .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok());
    let submission = submitted
        .as_ref()
        .and_then(|v| v.pointer("/managed/submission/id"))
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    let attempt = submitted
        .as_ref()
        .and_then(|v| v.pointer("/managed/attempt"))
        .and_then(|v| v.as_u64())
        .unwrap_or(0)
        .to_string();
    // `done` by the worker before acceptance must fail; invert the verdict.
    let early = probe.run("worker done before acceptance", &exe, &["done", &item], &worker_env, None);
    if let Some(step) = probe.steps.last_mut() {
        let refused = early.is_none() && probe.failed_step.as_deref().is_some_and(|f| f.starts_with("worker done before acceptance"));
        if refused {
            probe.failed_step = None;
            step["ok"] = serde_json::Value::Bool(true);
            step["note"] = serde_json::Value::String("refused as required".to_string());
        } else {
            step["ok"] = serde_json::Value::Bool(false);
            probe.failed_step = Some("worker closed before acceptance".to_string());
        }
    }
    probe.run("lead accept", &exe, &["accept", &item, "--check", "integration", "--target", "HEAD", "--evidence", "probe", "--submission", &submission, "--attempt", &attempt], &lead_env, None);
    let closed = probe.run("lead done", &exe, &["done", &item], &lead_env, None);
    if let Some(text) = closed {
        if !text.contains("authority: coordinator") {
            probe.failed_step = Some("lead done did not close as coordinator".to_string());
        }
    }

    // Drop lifecycle through the installed coord, then the hook identity.
    if let Some(coord) = coord {
        let lead_id = probe.run("coord lead whoami", coord, &["whoami", "--json"], &lead_env, None)
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
            .and_then(|v| v.get("agent_id").and_then(|a| a.as_str()).map(str::to_string))
            .unwrap_or_default();
        let added = probe.run("coord drop add", coord, &["drop", "add", "probe.md", "--for", &lead_id, "--note", "probe", "--json"], &worker_env, None)
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
            .and_then(|v| v.get("drop").and_then(|d| d.get("id")).and_then(|i| i.as_str()).map(str::to_string))
            .unwrap_or_default();
        let before = probe.run("coord interrupts before ack", coord, &["interrupts", "--json"], &lead_env, None).unwrap_or_default();
        if probe.failed_step.is_none() && !before.contains(&added) {
            probe.failed_step = Some("drop did not reach the recipient's interrupts".to_string());
        }
        probe.run("coord drop ack", coord, &["drop", "ack", &added, "--json"], &lead_env, None);
        let after = probe.run("coord interrupts after ack", coord, &["interrupts", "--json"], &lead_env, None).unwrap_or_default();
        if probe.failed_step.is_none() && after.contains(&added) {
            probe.failed_step = Some("acknowledged informational drop still interrupts".to_string());
        }
        // The hook must read coord as the same identity the shell used.
        if let Some(repo) = repo_root_from_exe() {
            let hook = repo.join("hooks").join("claude").join("agent-do-prompt-router.py");
            if hook.is_file() {
                let payload = serde_json::json!({"prompt": "build the probe feature now", "cwd": root.display().to_string(), "session_id": "probe-lead"}).to_string();
                let hook_env = [
                    ("AGENT_DO_HOME", home.display().to_string()),
                    ("HOME", home.display().to_string()),
                    ("AGENT_DO_HOOK_AI", "off".to_string()),
                ];
                let hook_path = hook.to_string_lossy().to_string();
                let output = probe.run("hook reads as the shell identity", Path::new("python3"), &[hook_path.as_str()], &hook_env, Some(&payload)).unwrap_or_default();
                if probe.failed_step.is_none() && output.contains(&added) {
                    probe.failed_step = Some("hook still nudged a drop the shell acknowledged (identity split)".to_string());
                }
            } else {
                probe.steps.push(serde_json::json!({"step": "hook identity", "ok": false, "error": format!("{} missing", hook.display())}));
                probe.failed_step = Some("hook script missing".to_string());
            }
        }
    } else {
        probe.steps.push(serde_json::json!({"step": "coord", "ok": false, "error": "agent-coord not found"}));
        probe.failed_step = Some("agent-coord not found".to_string());
    }

    let passed = probe.failed_step.is_none();
    let _ = std::fs::remove_dir_all(&root);
    serde_json::json!({
        "ran": true,
        "passed": passed,
        "failed_step": probe.failed_step,
        "fixture": root.display().to_string(),
        "steps": probe.steps,
    })
}
