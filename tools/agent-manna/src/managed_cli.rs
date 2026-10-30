//! CLI surface for the managed lifecycle: identity, coordinator grants,
//! submission, acceptance, release, closure assessment, audit history, and
//! the adoption doctor. Private helpers of the binary (output, identity,
//! coord liveness, trailer evidence) are reachable here because this is a
//! child module of `main`.

use std::path::{Path, PathBuf};

use chrono::Utc;
use clap::Subcommand;
use serde::Serialize;

use manna_core::error::MannaError;
use manna_core::issue::{Issue, IssueStatus, IssueType, SessionIdentity};
use manna_core::managed::{
    assessment_digest, closure_blockers, grant_id, Acceptance, Authority, Correction, Grant,
    GrantFile, GrantScope, LifecycleEvent, ManagedRecord, ManagedStore,
    PinnedTarget, Release, Revocation, Submission, CAPABILITY,
};
use manna_core::reconcile::manna_trailer_ids;
use manna_core::state::direct_coord_program;
use manna_core::store::MannaStore;

use crate::{
    commit_touches_source, coord_peer_statuses, coord_status_for_owner, find_issue,
    handle_manna_error, load_board_workflow, output_error, output_error_json, output_success,
    output_success_json, require_session_identity, IssueData, EXIT_NEEDS_AUTHORIZATION,
    EXIT_USER_ERROR,
};

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
    /// Release the current attempt so a replacement can claim (coordinator)
    Release {
        id: String,
        #[arg(long)]
        reason: String,
        /// Attest that the previous worker has stopped (coord must not see it active)
        #[arg(long)]
        worker_stopped: bool,
        /// The replacement works in this isolated checkout, so the old files are never shared
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
    /// Report whether the managed lifecycle is live on this machine, not only in source
    Doctor {
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

fn now_label() -> chrono::DateTime<Utc> {
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

fn audit(
    store: &ManagedStore,
    action: &str,
    issue_id: &str,
    session: &SessionIdentity,
    authority: &str,
    attempt: Option<u32>,
    reason: Option<&str>,
    evidence: Option<&str>,
    detail: Option<serde_json::Value>,
) {
    let event = LifecycleEvent {
        at: now_label(),
        action: action.to_string(),
        issue_id: issue_id.to_string(),
        actor: session.id().to_string(),
        authority: authority.to_string(),
        attempt,
        reason: reason.map(str::to_string),
        evidence: evidence.map(str::to_string),
        detail,
    };
    if let Err(error) = store.append_event(&event) {
        eprintln!("Warning: lifecycle audit not written: {}", error);
    }
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
            let result = board.with_board_lock(|| {
                let mut grants = store.load_grants().map_err(MannaError::MutationRejected)?;
                if grants.grants.iter().any(|existing| existing.id == written.id) {
                    return Err(MannaError::MutationRejected(format!(
                        "grant {} already exists",
                        written.id
                    )));
                }
                grants.grants.push(written.clone());
                store.save_grants(&grants).map_err(MannaError::MutationRejected)?;
                Ok(())
            });
            if let Err(error) = result {
                rejected(error, json);
            }
            audit(
                &store,
                "grant",
                "board",
                &session,
                "operator",
                None,
                Some(&grant.reason),
                None,
                Some(serde_json::json!({"grant": grant.id, "coordinator": grant.coordinator_id, "scope": grant.scope})),
            );
            emit(GrantData { grant }, json)
        }
        CoordinatorCommands::Revoke { grant_id, reason, json } => {
            let session = require_session_identity();
            if !session.is_operator() {
                fail(
                    "only the operator revokes a grant",
                    EXIT_NEEDS_AUTHORIZATION,
                    json,
                );
            }
            let actor = session.id().to_string();
            let reason_text = reason.trim().to_string();
            let revoked_id = grant_id.clone();
            let result = board.with_board_lock(|| {
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
                store.save_grants(&grants).map_err(MannaError::MutationRejected)?;
                Ok(snapshot)
            });
            let grant = match result {
                Ok(grant) => grant,
                Err(error) => rejected(error, json),
            };
            audit(
                &store,
                "revoke",
                "board",
                &session,
                "operator",
                None,
                Some(&reason),
                None,
                Some(serde_json::json!({"grant": grant.id})),
            );
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

fn require_coordination(
    session: &SessionIdentity,
    issue: &Issue,
    grants: &GrantFile,
    verb: &str,
    json: bool,
) -> Authority {
    let authority = Authority::resolve(session, issue, grants);
    if !authority.coordinates() {
        fail(
            &format!(
                "{} needs coordinator authority over {}: an operator terminal or a live grant covering this item or its track and held by this session's proof (level here: {}). A coord role, a pulse row, or a claim label is not authority",
                verb, issue.id, authority.level
            ),
            EXIT_NEEDS_AUTHORIZATION,
            json,
        );
    }
    authority
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
            worker_stopped,
            isolated_checkout,
            json,
        } => cmd_release(id, reason, worker_stopped, isolated_checkout, json),
        ManagedCommands::History { id, json } => cmd_history(id, json),
        ManagedCommands::Doctor { json } => cmd_doctor(json),
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
    let authority = require_coordination(&session, &issue, &grants, "managed require", json);
    let grant_label = authority
        .grant
        .clone()
        .unwrap_or_else(|| "operator".to_string());
    let actor = session.id().to_string();
    let result = board.with_locked_issue(&id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
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
        for check in &checks {
            if !record.required.iter().any(|existing| existing == check) {
                record.required.push(check.clone());
            }
        }
        let snapshot = record.clone();
        store.save_managed(&managed)?;
        Ok(snapshot)
    });
    let record = match result {
        Ok(record) => record,
        Err(error) => rejected(error, json),
    };
    audit(
        &store,
        "require",
        &id,
        &session,
        &authority.level,
        Some(record.attempt),
        reason.as_deref(),
        None,
        Some(serde_json::json!({"required": record.required})),
    );
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
        },
        json,
    )
}

/// `manna submit <id> --report <file|-> [--revision <ref>]`: the claim-holder
/// records its result for the current attempt. The item stays in_progress;
/// submission is not acceptance.
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
        let submission = Submission {
            attempt: record.attempt,
            by: actor.clone(),
            at: now_label(),
            revision: resolved_revision.clone(),
            report: text.clone(),
            status: "submitted".to_string(),
            correction: None,
        };
        if let Some(previous) = record.submission.replace(submission) {
            record.history.push(previous);
        }
        let snapshot = record.clone();
        store.save_managed(&managed)?;
        Ok(snapshot)
    });
    let record = match result {
        Ok(record) => record,
        Err(error) => rejected(error, json),
    };
    let authority = if session.is_operator() { "operator" } else { "owner" };
    audit(
        &store,
        "submit",
        &id,
        &session,
        authority,
        Some(record.attempt),
        None,
        resolved_revision.as_deref(),
        Some(serde_json::json!({"report_chars": text.chars().count()})),
    );
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
    let authority = require_coordination(&session, &issue, &grants, "managed correct", json);
    if reason.trim().is_empty() {
        fail("--reason must not be empty", EXIT_USER_ERROR, json);
    }
    let actor = session.id().to_string();
    let result = board.with_locked_issue(&id, |_, _| {
        let mut managed = store.load_managed()?;
        let record = managed
            .items
            .get_mut(&id)
            .ok_or_else(|| format!("{} is not a managed item", id))?;
        let submission = record
            .current_submission()
            .cloned()
            .ok_or_else(|| format!("no submission for attempt {} to correct", record.attempt))?;
        let mut updated = submission;
        updated.status = "correction_requested".to_string();
        updated.correction = Some(Correction {
            by: actor.clone(),
            at: now_label(),
            reason: reason.trim().to_string(),
        });
        record.submission = Some(updated);
        let snapshot = record.clone();
        store.save_managed(&managed)?;
        Ok(snapshot)
    });
    let record = match result {
        Ok(record) => record,
        Err(error) => rejected(error, json),
    };
    audit(
        &store,
        "correct",
        &id,
        &session,
        &authority.level,
        Some(record.attempt),
        Some(reason.trim()),
        None,
        None,
    );
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
        },
        json,
    )
}

/// `manna accept <id> --check <name> --target <ref> --evidence <text>`: an
/// authorized coordinator records one required check as accepted for the
/// current attempt at an explicitly pinned integration target.
pub fn cmd_accept(
    id: String,
    check: String,
    target: String,
    evidence: String,
    repin: bool,
    json: bool,
) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    let authority = require_coordination(&session, &issue, &grants, "accept", json);
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
    let actor = session.id().to_string();
    let level = authority.level.clone();
    let check_name = check.trim().to_string();
    let result = board.with_locked_issue(&id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
        let mut managed = store.load_managed()?;
        let record = managed
            .items
            .get_mut(&id)
            .ok_or_else(|| format!("{} is not a managed item", id))?;
        if !record.required.iter().any(|required| required == &check_name) {
            return Err(format!(
                "`{}` is not a required check on {} (required: {})",
                check_name,
                id,
                record.required.join(", ")
            ));
        }
        if record.current_submission().is_none() {
            return Err(format!(
                "no submission for attempt {}; acceptance records a verdict on a submitted result, not on an empty attempt",
                record.attempt
            ));
        }
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
            target_sha: resolved.sha.clone(),
            by: actor.clone(),
            authority: level.clone(),
            at: now_label(),
            evidence: evidence.trim().to_string(),
        });
        let snapshot = record.clone();
        store.save_managed(&managed)?;
        Ok(snapshot)
    });
    let record = match result {
        Ok(record) => record,
        Err(error) => rejected(error, json),
    };
    audit(
        &store,
        "accept",
        &id,
        &session,
        &authority.level,
        Some(record.attempt),
        None,
        Some(evidence.trim()),
        Some(serde_json::json!({"check": check.trim(), "target": target, "target_sha": resolved.sha, "target_kind": resolved.kind})),
    );
    emit(
        ManagedData {
            issue: IssueData {
                age: (&issue).into(),
                issue,
            },
            managed: record,
            authority,
        },
        json,
    )
}

fn cmd_release(
    id: String,
    reason: String,
    worker_stopped: bool,
    isolated_checkout: Option<String>,
    json: bool,
) -> ! {
    let board = open_board();
    let (issues, _) = load_board_workflow(&board);
    let issue = find_issue(&issues, &id);
    let store = managed_store();
    let session = require_session_identity();
    let grants = load_grants_or_fail(&store, json);
    let authority = require_coordination(&session, &issue, &grants, "managed release", json);
    if reason.trim().is_empty() {
        fail("--reason must not be empty", EXIT_USER_ERROR, json);
    }
    // Liveness of the worker being replaced. A failed probe is unknown, and
    // unknown is not death: without coord's word or an explicit basis the
    // release refuses rather than seat a second writer in the same files.
    let worker = issue.claimed_by.clone();
    let liveness = match worker.as_deref() {
        Some(owner) => match coord_peer_statuses() {
            Ok(statuses) => coord_status_for_owner(&statuses, owner)
                .cloned()
                .unwrap_or_else(|| "unknown".to_string()),
            Err(error) => format!("unknown ({})", error),
        },
        None => "unclaimed".to_string(),
    };
    let basis = if worker.is_none() {
        "unclaimed"
    } else if liveness == "dead" || liveness == "stopped" || liveness == "stale" {
        "coord_dead"
    } else if let Some(path) = isolated_checkout.as_deref() {
        if path.trim().is_empty() {
            fail("--isolated-checkout needs a path", EXIT_USER_ERROR, json);
        }
        "isolated_checkout"
    } else if worker_stopped {
        if liveness == "active" {
            fail(
                &format!(
                    "coord reports {} active; --worker-stopped contradicts a live observation. Stop the worker (`agent-do coord stop` in its session) or release with --isolated-checkout <path>",
                    worker.as_deref().unwrap_or("the worker")
                ),
                EXIT_NEEDS_AUTHORIZATION,
                json,
            );
        }
        "worker_stopped"
    } else {
        fail(
            &format!(
                "worker {} liveness is {}; unknown is not death. Release needs coord to report it dead/stopped/stale, or --worker-stopped (attested, refused when coord sees it active), or --isolated-checkout <path> for the replacement",
                worker.as_deref().unwrap_or("?"),
                liveness
            ),
            EXIT_NEEDS_AUTHORIZATION,
            json,
        );
    };
    let actor = session.id().to_string();
    let expected_worker = worker.clone();
    let liveness_label = liveness.clone();
    let isolation = isolated_checkout.clone();
    let reason_text = reason.trim().to_string();
    let result = board.with_locked_issue(&id, |current, _| {
        if current.status == IssueStatus::Done {
            return Err(format!("{} is already done", id));
        }
        if current.claimed_by != expected_worker {
            return Err(format!(
                "claim changed after inspection (expected {:?}, found {:?}); nothing was released",
                expected_worker, current.claimed_by
            ));
        }
        let mut managed = store.load_managed()?;
        let record = managed
            .items
            .get_mut(&id)
            .ok_or_else(|| format!("{} is not a managed item", id))?;
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
        });
        if let Some(previous) = record.submission.take() {
            record.history.push(previous);
        }
        record.attempt = released_attempt + 1;
        let snapshot = record.clone();
        store.save_managed(&managed)?;
        Ok(snapshot)
    });
    let record = match result {
        Ok(record) => record,
        Err(error) => rejected(error, json),
    };
    // The claim itself: released through the board's own administrative
    // path, compare-and-swap against the row inspected above.
    let released_issue = if issue.claimed_by.is_some() {
        let expected = issue.clone();
        match board.repair_issue(&id, move |current, _| {
            if current != &expected {
                return Err("row changed after inspection; the claim was not released".to_string());
            }
            current.release_dead_claim()
        }) {
            Ok(updated) => updated,
            Err(error) => rejected(error, json),
        }
    } else {
        issue.clone()
    };
    audit(
        &store,
        "release",
        &id,
        &session,
        &authority.level,
        Some(record.attempt),
        Some(reason.trim()),
        None,
        Some(serde_json::json!({"released_attempt": record.attempt - 1, "worker": worker, "worker_liveness": liveness, "basis": basis, "isolation": isolated_checkout})),
    );
    emit(
        ManagedData {
            issue: IssueData {
                age: (&released_issue).into(),
                issue: released_issue,
            },
            managed: record,
            authority,
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
    pub pinned: Option<PinnedTarget>,
    pub pinned_still_resolves: Option<bool>,
    pub matches_pinned: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Serialize)]
pub struct DeployedReport {
    pub sha: Option<String>,
    pub asserted_by: String,
}

#[derive(Serialize)]
pub struct Assessment {
    pub id: String,
    pub title: String,
    pub status: String,
    pub claimed_by: Option<String>,
    pub claimant_liveness: String,
    pub managed: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub record: Option<ManagedRecord>,
    pub attempt: Option<u32>,
    pub required_checks: Vec<String>,
    pub accepted_checks: Vec<Acceptance>,
    pub outstanding_checks: Vec<String>,
    pub submission_status: Option<String>,
    pub authority: Authority,
    pub integration_target: TargetReport,
    pub deployed_revision: DeployedReport,
    pub trailer_commits: Vec<TrailerCommit>,
    pub evidence_note: &'static str,
    pub closable: bool,
    pub blockers: Vec<String>,
    pub next_action: String,
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
    let claimant_liveness = match issue.claimed_by.as_deref() {
        Some(owner) => match coord_peer_statuses() {
            Ok(statuses) => coord_status_for_owner(&statuses, owner)
                .cloned()
                .unwrap_or_else(|| "unknown".to_string()),
            Err(error) => format!("unknown ({})", error),
        },
        None => "unclaimed".to_string(),
    };
    let current_head = git_output(&["rev-parse", "--verify", "HEAD^{commit}"]).ok();
    let pinned = record.and_then(|record| record.target.clone());
    let pinned_still_resolves = pinned
        .as_ref()
        .map(|pinned| git_output(&["rev-parse", "--verify", &format!("{}^{{commit}}", pinned.sha)]).is_ok());
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
    let (attempt, required, accepted, outstanding, submission_status) = match record {
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
            (
                Some(record.attempt),
                record.required.clone(),
                record.accepted_checks().into_iter().cloned().collect::<Vec<_>>(),
                record.outstanding_checks(),
                record.current_submission().map(|s| s.status.clone()),
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
            (None, Vec::new(), Vec::new(), Vec::new(), None)
        }
    };
    let closable = blockers.is_empty();
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
    } else if let Some(record) = record {
        if record.current_submission().is_none() {
            format!("worker: agent-do manna submit {} --report <file>", issue.id)
        } else if !outstanding.is_empty() && authority.coordinates() {
            format!(
                "agent-do manna accept {} --check {} --target <ref> --evidence \"<what was verified>\"",
                issue.id, outstanding[0]
            )
        } else if !outstanding.is_empty() {
            format!(
                "coordinator ({}) records acceptance for: {}",
                record.grant,
                outstanding.join(", ")
            )
        } else {
            "resolve the blockers above, then re-run assess".to_string()
        }
    } else {
        "resolve the blockers above, then re-run assess".to_string()
    };
    Assessment {
        id: issue.id.clone(),
        title: issue.title.clone(),
        status: issue.status.to_string(),
        claimed_by: issue.claimed_by.clone(),
        claimant_liveness,
        managed: record.is_some(),
        record: record.cloned(),
        attempt,
        required_checks: required,
        accepted_checks: accepted,
        outstanding_checks: outstanding,
        submission_status,
        authority,
        integration_target: TargetReport {
            requested: requested_target.map(str::to_string),
            sha: requested_sha,
            kind: requested_kind,
            is_current_head: is_head,
            current_head,
            pinned,
            pinned_still_resolves,
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
        closable,
        blockers,
        next_action,
        assessment: assessment_digest(issue, record),
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
}

/// Refuse or authorize a managed close. Returns `None` for unmanaged items.
/// The closure itself runs under the board lock with the sidecar re-read,
/// so an assessment that went stale between look and act is refused.
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
    if let Some(expected) = expected_assessment {
        let current = assessment_digest(issue, Some(&record));
        if expected != current {
            return Some(Err(MannaError::MutationRejected(format!(
                "stale assessment: {} was assessed as {} but is now {}; re-run `agent-do manna assess {}` and act on the current state",
                issue.id, expected, current, issue.id
            ))));
        }
    }
    let level: &'static str = match authority.level.as_str() {
        "operator" => "operator",
        "coordinator" => "coordinator",
        _ => "owner",
    };
    let id = issue.id.clone();
    let inner_id = id.clone();
    let expected_digest = expected_assessment.map(str::to_string);
    let precondition_store = managed_store();
    let result = board.complete_issue_on_acceptance(&id, move |current, _| {
        let live = precondition_store
            .record_for(&inner_id)?
            .ok_or_else(|| format!("{} lost its managed record between assessment and close", inner_id))?;
        let blockers = closure_blockers(current, &live);
        if !blockers.is_empty() {
            return Err(format!(
                "managed state changed before the close: {}",
                blockers.join("; ")
            ));
        }
        if let Some(expected) = expected_digest.as_deref() {
            let now = assessment_digest(current, Some(&live));
            if expected != now {
                return Err(format!(
                    "stale assessment: {} moved to {} under the lock; nothing was closed",
                    expected, now
                ));
            }
        }
        Ok(())
    });
    match result {
        Ok(completed) => {
            audit(
                &store,
                "close",
                &issue.id,
                session,
                level,
                Some(record.attempt),
                None,
                None,
                Some(serde_json::json!({
                    "accepted": record.accepted_checks().iter().map(|a| a.check.clone()).collect::<Vec<_>>(),
                    "target": record.target.as_ref().map(|t| t.sha.clone()),
                    "released": completed.released,
                })),
            );
            Some(Ok((
                completed,
                ManagedClose { authority: level },
            )))
        }
        Err(error) => Some(Err(error)),
    }
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

/// Record a lifecycle line for ordinary board verbs on managed items (claim,
/// abandon) so the audit holds the whole story. Abandon by the worker ends
/// its attempt: the next claimant is a new attempt.
pub fn note_claim(id: &str, session: &SessionIdentity) {
    let store = managed_store();
    if let Ok(Some(record)) = store.record_for(id) {
        audit(&store, "claim", id, session, "owner", Some(record.attempt), None, None, None);
    }
}

pub fn note_abandon(board: &MannaStore, id: &str, session: &SessionIdentity) {
    let store = managed_store();
    let Ok(Some(_)) = store.record_for(id) else {
        return;
    };
    let actor = session.id().to_string();
    let result = board.with_board_lock(|| {
        let mut managed = store.load_managed().map_err(MannaError::MutationRejected)?;
        let Some(record) = managed.items.get_mut(id) else {
            return Ok(None);
        };
        let ended = record.attempt;
        record.releases.push(Release {
            attempt: ended,
            by: actor.clone(),
            at: now_label(),
            reason: "worker abandoned the claim".to_string(),
            worker: Some(actor.clone()),
            worker_liveness: "self".to_string(),
            basis: "abandon".to_string(),
            isolation: None,
        });
        if let Some(previous) = record.submission.take() {
            record.history.push(previous);
        }
        record.attempt = ended + 1;
        let next = record.attempt;
        store.save_managed(&managed).map_err(MannaError::MutationRejected)?;
        Ok(Some(next))
    });
    match result {
        Ok(Some(next)) => audit(
            &store,
            "abandon",
            id,
            session,
            "owner",
            Some(next),
            Some("worker abandoned the claim"),
            None,
            None,
        ),
        Ok(None) => {}
        Err(error) => eprintln!("Warning: managed attempt not advanced on abandon: {}", error),
    }
}

// ----------------------------------------------------------------------------
// doctor: is this live, or only in source?
// ----------------------------------------------------------------------------

#[derive(Serialize)]
struct DoctorData {
    live: bool,
    binary: serde_json::Value,
    coord: serde_json::Value,
    hooks: serde_json::Value,
    board: serde_json::Value,
    verdict: String,
}

fn cmd_doctor(json: bool) -> ! {
    let exe = std::env::current_exe()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|_| "unknown".to_string());
    let binary = serde_json::json!({
        "path": exe,
        "version": env!("CARGO_PKG_VERSION"),
        "capabilities": [CAPABILITY],
        "note": "the wrapper picks target/release first, then target/debug, then PATH; this is the binary that answered",
    });

    // coord: does the installed agent-coord know drop ack/resolve?
    let coord_program = direct_coord_program(Path::new("agent-do"))
        .or_else(|| {
            std::env::current_exe().ok().and_then(|exe| {
                // tools/agent-manna/target/release/manna-core -> tools/agent-coord
                exe.ancestors()
                    .nth(4)
                    .map(|root| root.join("tools").join("agent-coord"))
                    .filter(|candidate| candidate.is_file())
            })
        });
    let (coord_ok, coord_detail) = match coord_program.as_ref() {
        Some(program) => match std::process::Command::new(program).arg("help").output() {
            Ok(out) => {
                let text = String::from_utf8_lossy(&out.stdout);
                let ack = text.contains("drop ack");
                let resolve = text.contains("drop resolve");
                (
                    ack && resolve,
                    serde_json::json!({"program": program.display().to_string(), "drop_ack": ack, "drop_resolve": resolve}),
                )
            }
            Err(error) => (
                false,
                serde_json::json!({"program": program.display().to_string(), "error": error.to_string()}),
            ),
        },
        None => (false, serde_json::json!({"program": null, "error": "agent-coord not found beside agent-do or this binary"})),
    };

    // hooks: the Claude settings must register the two hooks that surface
    // coord interrupts; an unregistered wrapper never fires.
    let settings = std::env::var("HOME")
        .map(|home| PathBuf::from(home).join(".claude").join("settings.json"))
        .ok();
    let settings_text = settings
        .as_ref()
        .and_then(|path| std::fs::read_to_string(path).ok());
    let registered = |name: &str| settings_text.as_deref().is_some_and(|text| text.contains(name));
    let prompt_router = registered("agent-do-prompt-router.py");
    let session_start = registered("agent-do-session-start.sh");
    let hooks = serde_json::json!({
        "settings": settings.as_ref().map(|p| p.display().to_string()),
        "readable": settings_text.is_some(),
        "prompt_router_registered": prompt_router,
        "session_start_registered": session_start,
    });

    // board
    let store = managed_store();
    let board_root = Path::new(".manna");
    let initialized = board_root.is_dir();
    let managed = store.load_managed().map(|file| file.items.len()).ok();
    let grants = store
        .load_grants()
        .map(|file| file.grants.iter().filter(|g| g.is_live()).count())
        .ok();
    let board = serde_json::json!({
        "initialized": initialized,
        "managed_items": managed,
        "live_grants": grants,
        "sidecars_present": store.present_files().iter().map(|p| p.display().to_string()).collect::<Vec<_>>(),
    });

    let live = coord_ok && prompt_router && session_start;
    let verdict = if live {
        "live: this binary, the installed agent-coord, and the registered Claude hooks all carry the managed lifecycle".to_string()
    } else {
        let mut missing = Vec::new();
        if !coord_ok {
            missing.push("agent-coord without drop ack/resolve");
        }
        if !prompt_router {
            missing.push("agent-do-prompt-router.py not registered in ~/.claude/settings.json");
        }
        if !session_start {
            missing.push("agent-do-session-start.sh not registered in ~/.claude/settings.json");
        }
        format!("not live: {}", missing.join("; "))
    };
    emit(
        DoctorData {
            live,
            binary,
            coord: coord_detail,
            hooks,
            board,
            verdict,
        },
        json,
    )
}
