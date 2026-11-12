//! Canonical Manna and handoff workflow scaffolding.
//!
//! A strict board is one recoverable state machine. `.manna/` owns lifecycle
//! state, `.handoff/` owns bound work orders, and an ignored transaction
//! journal closes the small crash window between those two filesystems.

use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use chrono::Utc;
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::MannaError;
use crate::issue::{
    Issue, IssueStatus, IssueType, LegacyMigrationAnnotation, LegacyMigrationDisposition,
    SessionIdentity,
};
use crate::reconcile::{prompt_pointer, strip_prompt_annotation};
use crate::store::MannaStore;
use crate::track::{is_paired, pairable};

pub const WORKFLOW_VERSION: u32 = 2;
pub const HANDOFF_DIR: &str = ".handoff";
pub const WORKFLOW_FILE: &str = ".manna/workflow.yaml";
pub const BOARD_FILE: &str = ".manna/board.yaml";
pub const HANDOFF_ORDER_FILE: &str = ".manna/handoff-order.yaml";
pub const HANDOFF_README: &str = ".handoff/README.md";
const FEDERATION_MANIFEST_FILE: &str = ".manna/federation.yaml";
pub const HANDOFF_ARCHIVE_DIR: &str = ".handoff/.archive";
const LEGACY_SOURCE_ARCHIVE_DIR: &str = ".handoff/.archive/legacy-sources";
const HANDOFF_SYNC_STAGE_DIR: &str = ".handoff/.sync";
const TRANSACTION_DIR: &str = ".manna/transactions";
const BOARD_INIT_TRANSACTION: &str = ".manna/transactions/board-init.yaml";
const LEGACY_MIGRATION_TRANSACTION: &str = ".manna/transactions/legacy-board-migration.yaml";
const BOARD_INIT_VERSION: u32 = 1;
const LEGACY_MIGRATION_VERSION: u32 = 1;
const HANDOFF_ORDER_VERSION: u32 = 1;
const HANDOFF_SYNC_TRANSACTION_ID: &str = "mn-handoff-sync";

const README_PREAMBLE: &str = r#"# agent-do handoffs

This directory is generated workflow state. `.manna/` owns status, tracks,
claims, and blockers. Each actionable Manna item owns exactly one Markdown
work order here, and the two are content-bound.

Rules:

- Create work through `agent-do manna create`; do not hand-build parallel
  prompt roots such as `.handoffs/`, `.dev/session-prompts/`, or
  `<campaign>/handoff-prompts/`.
- The Manna item `prompt` field points to a board-wide fixed-width name,
  `.handoff/<NN...>[b<MM...>]-mn-xxxxxx-<slug>.md`, after synchronization.
  Width is at least two digits and expands when the active plan exceeds 99.
- Frontmatter identifies the item, track, source, base commit, scope, inputs,
  and SHA-256 binding for the complete document.
- Edit a work order, then run `agent-do manna handoff seal mn-xxxxxx` before
  claiming it. A claim fails closed on any unsealed change.
- Board state stays in Manna. The handoff contains scope, authority,
  deliverables, and verification, never a second backlog.
- Priority lives in `.manna/handoff-order.yaml`. Run `agent-do manna sync`
  after board changes; never hand-maintain numbered filenames or this index.
- A bare numbered filename is safe to launch. `bMM...` means the item is held
  until that numbered priority closes. The full dependency truth remains
  `blocked_by`.
- Completed pairs return to unnumbered sealed history on sync, so no numbered
  filename advertises work that is already done.
- Commit `.manna/workflow.yaml`, `.manna/handoff-order.yaml`,
  `.manna/federation.yaml`, `.manna/issues.jsonl`, and `.handoff/`.
"#;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorkflowConfig {
    pub version: u32,
    pub handoff_dir: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum BoardMode {
    Strict,
    Legacy,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BoardConfig {
    version: u32,
    workflow: BoardMode,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    migrated_from_legacy_at: Option<chrono::DateTime<Utc>>,
}

impl BoardConfig {
    fn strict() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Strict,
            migrated_from_legacy_at: None,
        }
    }

    fn legacy() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Legacy,
            migrated_from_legacy_at: None,
        }
    }
}

impl Default for WorkflowConfig {
    fn default() -> Self {
        WorkflowConfig {
            version: WORKFLOW_VERSION,
            handoff_dir: HANDOFF_DIR.to_string(),
        }
    }
}

impl WorkflowConfig {
    fn validate_loadable(&self) -> Result<(), String> {
        if !(1..=WORKFLOW_VERSION).contains(&self.version) {
            return Err(format!(
                "unsupported Manna workflow version {} (current {})",
                self.version, WORKFLOW_VERSION
            ));
        }
        if self.handoff_dir != HANDOFF_DIR {
            return Err(format!(
                "workflow handoff_dir must be {}, got {}",
                HANDOFF_DIR, self.handoff_dir
            ));
        }
        Ok(())
    }

    pub fn validate(&self) -> Result<(), String> {
        self.validate_loadable()?;
        if self.version != WORKFLOW_VERSION {
            return Err(format!(
                "Manna workflow version {} must be upgraded to {}; run `agent-do manna init`",
                self.version, WORKFLOW_VERSION
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct WorkflowInit {
    pub config: WorkflowConfig,
    pub gitignore_updated: bool,
    pub upgraded_items: usize,
    pub restored_config: bool,
    pub recovered_transactions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandoffFrontmatter {
    workflow: u32,
    manna: String,
    track: Option<String>,
    source: Option<String>,
    base_commit: String,
    scope: String,
    inputs: Vec<String>,
    binding: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum PairAction {
    Create,
    Attach,
    Rebind,
    Rename,
    Detach,
    Delete,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandoffRename {
    issue_id: String,
    from: String,
    to: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandoffSyncTransaction {
    before: Vec<Issue>,
    after: Vec<Issue>,
    renames: Vec<HandoffRename>,
    order_before: Option<String>,
    order_after: String,
    readme_before: Option<String>,
    readme_after: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PairTransaction {
    version: u32,
    action: PairAction,
    issue_id: String,
    before: Option<Issue>,
    after: Option<Issue>,
    handoff: String,
    archive: Option<String>,
    document: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    sync: Option<HandoffSyncTransaction>,
    integrity: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandoffOrder {
    version: u32,
    items: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HandoffSyncResult {
    pub renamed: usize,
    pub held_claimed: Vec<String>,
    pub ordered_items: usize,
    pub changed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HandoffOrderEntry {
    pub issue_id: String,
    pub priority: usize,
    pub expected_path: String,
    pub actual_path: Option<String>,
    pub held_claimed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HandoffPresentationDrift {
    pub issue_id: Option<String>,
    pub rule: &'static str,
    pub detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct MigrationDocument {
    issue_id: String,
    handoff: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    previous_document: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    source_document: Option<String>,
    document: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct MigrationSourceArchive {
    source: String,
    archive: String,
    document: String,
    issue_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct MigrationSource {
    project_relative: Option<PathBuf>,
    provenance: String,
    document: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct InitManagedText {
    before: Option<String>,
    after: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BoardInitTransaction {
    version: u32,
    issues: InitManagedText,
    sessions: InitManagedText,
    board: InitManagedText,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    gitignore: Option<InitManagedText>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    workflow: Option<InitManagedText>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    order: Option<InitManagedText>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    readme: Option<InitManagedText>,
    integrity: String,
}

#[derive(Debug)]
struct BoardInitPreparation {
    transaction: BoardInitTransaction,
    changed: bool,
    strict: bool,
    gitignore_updated: bool,
    restored_config: bool,
    old_workflow: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyBoardTransaction {
    version: u32,
    before: Vec<Issue>,
    after: Vec<Issue>,
    documents: Vec<MigrationDocument>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    source_archives: Vec<MigrationSourceArchive>,
    gitignore_before: Option<String>,
    gitignore_after: String,
    board_before: Option<String>,
    board_after: String,
    workflow_before: Option<String>,
    workflow_after: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    order_before: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    order_after: Option<String>,
    readme_before: Option<String>,
    readme_after: String,
    integrity: String,
}

#[derive(Debug, Clone)]
pub struct LegacyMigrationResult {
    pub migrated: bool,
    pub recovered_transaction: bool,
    pub paired_items: usize,
    pub historical_rows: usize,
    pub exempt_rows: usize,
    pub released_claims: usize,
}

#[derive(Debug, PartialEq, Eq)]
enum TransactionOutcome {
    Applied,
    DiscardedConflict(String),
}

pub fn workflow_path(base: &Path) -> PathBuf {
    base.join(WORKFLOW_FILE)
}

fn load_board_config(base: &Path) -> Result<Option<BoardConfig>, String> {
    let relative = safe_relative_path(base, Path::new(BOARD_FILE), true)?;
    let path = base.join(relative);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let config: BoardConfig = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid {}: {}", path.display(), error))?;
    if config.version != 1 {
        return Err(format!(
            "unsupported Manna board identity version {}",
            config.version
        ));
    }
    Ok(Some(config))
}

fn path_exists(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

fn reject_symlink(path: &Path, label: &str) -> Result<(), String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(format!("refusing symlinked {}: {}", label, path.display()))
        }
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("failed to inspect {}: {}", path.display(), error)),
    }
}

fn normalize_relative(path: &Path) -> Result<PathBuf, String> {
    let mut clean = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Normal(value) => clean.push(value),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(format!("handoff path must stay inside {}", HANDOFF_DIR));
            }
        }
    }
    Ok(clean)
}

fn safe_relative_path(
    base: &Path,
    relative: &Path,
    leaf_may_be_missing: bool,
) -> Result<PathBuf, String> {
    let relative = normalize_relative(relative)?;
    let root = base
        .canonicalize()
        .map_err(|error| format!("failed to resolve project root: {}", error))?;
    let mut cursor = base.to_path_buf();
    let component_count = relative.components().count();
    for (index, component) in relative.components().enumerate() {
        let Component::Normal(value) = component else {
            return Err(format!("unsafe workflow path: {}", relative.display()));
        };
        cursor.push(value);
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() {
                    return Err(format!(
                        "workflow path crosses a symlink: {}",
                        cursor.display()
                    ));
                }
                if index + 1 < component_count && !metadata.is_dir() {
                    return Err(format!(
                        "workflow parent is not a directory: {}",
                        cursor.display()
                    ));
                }
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::NotFound
                    && (leaf_may_be_missing || index + 1 < component_count) => {}
            Err(error) => return Err(format!("failed to inspect {}: {}", cursor.display(), error)),
        }
    }
    if let Some(parent) = cursor.parent() {
        let existing_parent = if parent.exists() {
            parent.to_path_buf()
        } else {
            parent
                .ancestors()
                .find(|candidate| candidate.exists())
                .unwrap_or(base)
                .to_path_buf()
        };
        let resolved = existing_parent.canonicalize().map_err(|error| {
            format!("failed to resolve {}: {}", existing_parent.display(), error)
        })?;
        if !resolved.starts_with(&root) {
            return Err(format!(
                "workflow path escapes the project through {}",
                existing_parent.display()
            ));
        }
    }
    Ok(relative)
}

pub(crate) fn safe_create_dir_all(base: &Path, relative: &Path) -> Result<(), String> {
    let relative = normalize_relative(relative)?;
    let mut cursor = base.to_path_buf();
    for component in relative.components() {
        let Component::Normal(value) = component else {
            return Err(format!("unsafe workflow directory: {}", relative.display()));
        };
        cursor.push(value);
        reject_symlink(&cursor, "workflow directory")?;
        if !cursor.exists() {
            match fs::create_dir(&cursor) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(format!("failed to create {}: {}", cursor.display(), error))
                }
            }
        }
        if !cursor.is_dir() {
            return Err(format!(
                "workflow path is not a directory: {}",
                cursor.display()
            ));
        }
    }
    Ok(())
}

pub(crate) fn sync_parent(path: &Path) -> Result<(), String> {
    let Some(parent) = path.parent() else {
        return Ok(());
    };
    File::open(parent)
        .and_then(|file| file.sync_all())
        .map_err(|error| format!("failed to sync {}: {}", parent.display(), error))
}

pub(crate) fn atomic_write(path: &Path, contents: &[u8], replace: bool) -> Result<(), String> {
    reject_symlink(path, "workflow file")?;
    let parent = path
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| format!("invalid file name: {}", path.display()))?;
    let temp = parent.join(format!(
        ".{}.{}.{}.tmp",
        name,
        std::process::id(),
        Utc::now().timestamp_nanos_opt().unwrap_or_default()
    ));
    reject_symlink(parent, "workflow parent")?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("failed to create {}: {}", temp.display(), error))?;
    if let Err(error) = file.write_all(contents).and_then(|_| file.sync_all()) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to write {}: {}", temp.display(), error));
    }
    drop(file);
    let install = if replace {
        fs::rename(&temp, path)
    } else {
        // A hard link is an atomic create-if-absent operation when source and
        // destination share a directory. Unlike an existence check followed
        // by rename, it cannot overwrite a transaction another process won.
        fs::hard_link(&temp, path).and_then(|_| fs::remove_file(&temp))
    };
    if let Err(error) = install {
        let _ = fs::remove_file(&temp);
        return Err(
            if !replace && error.kind() == std::io::ErrorKind::AlreadyExists {
                format!("refusing to overwrite existing file {}", path.display())
            } else {
                format!("failed to install {}: {}", path.display(), error)
            },
        );
    }
    sync_parent(path)
}

fn atomic_write_replace(path: &Path, contents: &str) -> Result<(), String> {
    atomic_write(path, contents.as_bytes(), true)
}

pub fn load_workflow(base: &Path) -> Result<Option<WorkflowConfig>, String> {
    let relative = safe_relative_path(base, Path::new(WORKFLOW_FILE), true)?;
    let path = base.join(relative);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let config: WorkflowConfig = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid {}: {}", path.display(), error))?;
    config.validate_loadable()?;
    Ok(Some(config))
}

pub fn workflow_markers_present(_base: &Path, issues: &[Issue]) -> bool {
    issues.iter().any(|issue| {
        issue.handoff_digest.is_some()
            || issue.prompt.as_deref().is_some_and(|pointer| {
                normalize_relative(Path::new(pointer))
                    .is_ok_and(|path| path.starts_with(HANDOFF_DIR))
            })
    })
}

/// Load the board mode without permitting deletion of one config file to
/// downgrade a strict board to legacy behavior.
pub fn load_workflow_for_board(
    base: &Path,
    issues: &[Issue],
) -> Result<Option<WorkflowConfig>, String> {
    let board = load_board_config(base)?.ok_or_else(|| {
        if issues.is_empty() {
            "Manna board identity is missing; run `agent-do manna init` before using the board"
                .to_string()
        } else {
            "Manna board identity is missing on a nonempty legacy board; run `agent-do manna migrate` before using the board"
                .to_string()
        }
    })?;
    match board.workflow {
        BoardMode::Strict => match load_workflow(base)? {
            Some(config) => {
                config.validate()?;
                Ok(Some(config))
            }
            None => Err(format!(
                "strict Manna board identity exists but {} is missing; run `agent-do manna init` to restore it",
                WORKFLOW_FILE
            )),
        },
        BoardMode::Legacy => {
            if load_workflow(base)?.is_some() || workflow_markers_present(base, issues) {
                return Err(
                    "legacy board identity conflicts with strict workflow state; run `agent-do manna migrate`"
                        .to_string(),
                );
            }
            Ok(None)
        }
    }
}

fn git_path_ignored(base: &Path, relative: &Path) -> Result<bool, String> {
    let inside = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--is-inside-work-tree"])
        .output()
        .map_err(|error| format!("git rev-parse unavailable: {}", error))?;
    if !inside.status.success() || String::from_utf8_lossy(&inside.stdout).trim() != "true" {
        return Ok(false);
    }
    let output = Command::new("git")
        .current_dir(base)
        .args(["check-ignore", "--no-index", "--quiet", "--"])
        .arg(relative)
        .output()
        .map_err(|error| format!("git check-ignore unavailable: {}", error))?;
    match output.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        code => Err(format!("git check-ignore failed with status {:?}", code)),
    }
}

fn durable_paths() -> [&'static str; 6] {
    [
        ".manna/issues.jsonl",
        ".manna/sessions.jsonl",
        BOARD_FILE,
        WORKFLOW_FILE,
        HANDOFF_ORDER_FILE,
        HANDOFF_README,
    ]
}

fn durable_visibility_paths() -> impl Iterator<Item = &'static str> {
    durable_paths()
        .into_iter()
        .chain([FEDERATION_MANIFEST_FILE])
}

fn git_path_tracked(base: &Path, relative: &Path) -> Result<bool, String> {
    let inside = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--is-inside-work-tree"])
        .output()
        .map_err(|error| format!("git rev-parse unavailable: {}", error))?;
    if !inside.status.success() || String::from_utf8_lossy(&inside.stdout).trim() != "true" {
        return Ok(false);
    }
    let output = Command::new("git")
        .current_dir(base)
        .args(["ls-files", "--error-unmatch", "--"])
        .arg(relative)
        .output()
        .map_err(|error| format!("git ls-files unavailable: {}", error))?;
    match output.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        code => Err(format!("git ls-files failed with status {:?}", code)),
    }
}

/// Durable board files can be Git-visible without being in the index. Lint
/// reports that distinction so an ignored-state repair cannot be mistaken for
/// actual history protection.
pub fn untracked_durable_paths(base: &Path) -> Result<Vec<PathBuf>, String> {
    durable_paths()
        .into_iter()
        .chain([
            ".manna/drift.yaml",
            ".manna/coordinators.json",
            ".manna/managed.json",
            ".manna/lifecycle.jsonl",
        ])
        .filter(|relative| base.join(relative).is_file())
        .filter_map(
            |relative| match git_path_tracked(base, Path::new(relative)) {
                Ok(true) => None,
                Ok(false) => Some(Ok(PathBuf::from(relative))),
                Err(error) => Some(Err(error)),
            },
        )
        .collect()
}

fn read_optional_text(path: &Path, label: &str) -> Result<Option<String>, String> {
    reject_symlink(path, label)?;
    match fs::read_to_string(path) {
        Ok(text) => Ok(Some(text)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("failed to read {}: {}", path.display(), error)),
    }
}

fn workflow_gitignore_content(existing: &str) -> String {
    let marker = "# agent-do workflow: .manna and .handoff are durable state";
    let mut updated = existing.to_string();
    if !updated.is_empty() && !updated.ends_with('\n') {
        updated.push('\n');
    }
    if !existing.contains(marker) {
        updated.push_str(&format!(
            "\n{}\n!.manna/\n.manna/*\n!.manna/issues.jsonl\n!.manna/sessions.jsonl\n!.manna/board.yaml\n!.manna/workflow.yaml\n!.manna/handoff-order.yaml\n!.manna/federation.yaml\n!.manna/drift.yaml\n!.manna/coordinators.json\n!.manna/managed.json\n!.manna/lifecycle.jsonl\n.manna/board.lock\n.manna/transactions/\n!.handoff/\n!.handoff/**\n",
            marker
        ));
    } else {
        for rule in [
            "!.manna/board.yaml",
            "!.manna/handoff-order.yaml",
            "!.manna/federation.yaml",
            "!.manna/coordinators.json",
            "!.manna/managed.json",
            "!.manna/lifecycle.jsonl",
            ".manna/transactions/",
        ] {
            if !updated.lines().any(|line| line == rule) {
                updated.push_str(rule);
                updated.push('\n');
            }
        }
    }
    updated
}

fn ensure_workflow_tracked(base: &Path) -> Result<bool, String> {
    let ignored_before = durable_visibility_paths()
        .map(|path| git_path_ignored(base, Path::new(path)))
        .collect::<Result<Vec<_>, _>>()?;
    if ignored_before.iter().all(|ignored| !ignored) {
        return Ok(false);
    }

    let gitignore = base.join(".gitignore");
    reject_symlink(&gitignore, ".gitignore")?;
    let existing = fs::read_to_string(&gitignore).unwrap_or_default();
    let updated = workflow_gitignore_content(&existing);
    if updated != existing {
        atomic_write_replace(&gitignore, &updated)?;
    }
    let still_ignored: Vec<&str> = durable_visibility_paths()
        .filter_map(|path| {
            git_path_ignored(base, Path::new(path))
                .ok()
                .filter(|ignored| *ignored)
                .map(|_| path)
        })
        .collect();
    if !still_ignored.is_empty() {
        return Err(format!(
            "durable Manna workflow state is still ignored by Git: {}",
            still_ignored.join(", ")
        ));
    }
    Ok(true)
}

fn validate_new_handoff_root(base: &Path) -> Result<(), String> {
    let handoff_dir = base.join(HANDOFF_DIR);
    reject_symlink(&handoff_dir, "handoff root")?;
    if !handoff_dir.is_dir() {
        return Ok(());
    }
    let mut entries = fs::read_dir(&handoff_dir)
        .map_err(|error| format!("failed to inspect {}: {}", handoff_dir.display(), error))?;
    let first = match entries.next() {
        None => return Ok(()),
        Some(Ok(entry)) => entry,
        Some(Err(error)) => {
            return Err(format!(
                "failed to inspect {}: {}",
                handoff_dir.display(),
                error
            ))
        }
    };
    if first.path() == base.join(HANDOFF_README)
        && entries.next().is_none()
        && first.path().is_file()
    {
        return Ok(());
    }
    Err(format!(
        "{} already contains non-workflow files; migrate or archive them before initializing a strict board",
        HANDOFF_DIR
    ))
}

fn current_base_commit(base: &Path) -> String {
    let output = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--verify", "HEAD"])
        .output();
    match output {
        Ok(result) if result.status.success() => {
            String::from_utf8_lossy(&result.stdout).trim().to_string()
        }
        _ => "unborn".to_string(),
    }
}

pub fn slugify(title: &str) -> String {
    let mut slug = String::new();
    let mut pending_dash = false;
    for character in title.chars() {
        if character.is_ascii_alphanumeric() {
            if pending_dash && !slug.is_empty() {
                slug.push('-');
            }
            slug.push(character.to_ascii_lowercase());
            pending_dash = false;
            if slug.len() >= 64 {
                break;
            }
        } else if !slug.is_empty() {
            pending_dash = true;
        }
    }
    while slug.ends_with('-') {
        slug.pop();
    }
    if slug.is_empty() {
        "item".to_string()
    } else {
        slug
    }
}

pub fn canonical_handoff_path(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
    requested: Option<&str>,
) -> Result<PathBuf, String> {
    config.validate()?;
    let relative = if let Some(raw) = requested.map(str::trim).filter(|path| !path.is_empty()) {
        let requested_path = Path::new(raw);
        if requested_path.is_absolute() {
            let base_abs = base
                .canonicalize()
                .map_err(|error| format!("failed to resolve project root: {}", error))?;
            requested_path
                .strip_prefix(&base_abs)
                .map_err(|_| format!("handoff path must live under {}/", HANDOFF_DIR))?
                .to_path_buf()
        } else {
            normalize_relative(requested_path)?
        }
    } else {
        Path::new(&config.handoff_dir).join(format!("{}-{}.md", issue.id, slugify(&issue.title)))
    };

    let relative = safe_relative_path(base, &relative, true)?;
    if !relative.starts_with(&config.handoff_dir)
        || relative
            .extension()
            .and_then(|extension| extension.to_str())
            != Some("md")
        || relative == Path::new(HANDOFF_README)
        || relative.starts_with(HANDOFF_ARCHIVE_DIR)
    {
        return Err(format!(
            "actionable item handoffs must be Markdown files under {}/",
            HANDOFF_DIR
        ));
    }
    Ok(relative)
}

/// Rows that own a canonical handoff: every strict item, plus any track that
/// was given a dispatch work order. Paired tracks enter priority and the
/// generated index exactly like items.
fn paired_items(issues: &[Issue]) -> Vec<&Issue> {
    issues
        .iter()
        .filter(|issue| pairable(issue.issue_type) && is_paired(issue))
        .collect()
}

fn planned_items(issues: &[Issue]) -> Vec<&Issue> {
    paired_items(issues)
        .into_iter()
        .filter(|issue| issue.status != IssueStatus::Done)
        .collect()
}

fn has_live_claim(issue: &Issue) -> bool {
    issue.status != IssueStatus::Done && issue.claimed_by.is_some()
}

fn canonical_order(items: Vec<String>) -> HandoffOrder {
    HandoffOrder {
        version: HANDOFF_ORDER_VERSION,
        items,
    }
}

fn serialize_order(order: &HandoffOrder) -> Result<String, String> {
    serde_yaml::to_string(order)
        .map_err(|error| format!("failed to serialize handoff priority: {}", error))
}

fn parse_order(text: &str) -> Result<HandoffOrder, String> {
    let order: HandoffOrder = serde_yaml::from_str(text)
        .map_err(|error| format!("invalid {}: {}", HANDOFF_ORDER_FILE, error))?;
    if order.version != HANDOFF_ORDER_VERSION {
        return Err(format!(
            "unsupported handoff priority version {} (current {})",
            order.version, HANDOFF_ORDER_VERSION
        ));
    }
    let mut seen = HashSet::new();
    for id in &order.items {
        if !seen.insert(id.clone()) {
            return Err(format!(
                "{} contains duplicate item {}",
                HANDOFF_ORDER_FILE, id
            ));
        }
    }
    Ok(order)
}

fn read_order_text(base: &Path) -> Result<Option<String>, String> {
    read_optional_text(&base.join(HANDOFF_ORDER_FILE), "handoff priority")
}

fn normalize_order(
    issues: &[Issue],
    stored: Option<&HandoffOrder>,
) -> Result<HandoffOrder, String> {
    let candidates = planned_items(issues);
    let candidate_ids = candidates
        .iter()
        .map(|issue| issue.id.as_str())
        .collect::<HashSet<_>>();
    let mut items = Vec::with_capacity(candidates.len());
    let mut seen = HashSet::new();
    if let Some(stored) = stored {
        for id in &stored.items {
            if candidate_ids.contains(id.as_str()) && seen.insert(id.clone()) {
                items.push(id.clone());
            }
        }
    }
    for issue in candidates {
        if seen.insert(issue.id.clone()) {
            items.push(issue.id.clone());
        }
    }
    Ok(canonical_order(items))
}

fn migration_order(
    before: &[Issue],
    after: &[Issue],
    stored: Option<&HandoffOrder>,
) -> Result<HandoffOrder, String> {
    let candidates = planned_items(after);
    let candidate_ids = candidates
        .iter()
        .map(|issue| issue.id.as_str())
        .collect::<HashSet<_>>();
    let mut items = Vec::with_capacity(candidates.len());
    let mut seen = HashSet::new();
    if let Some(stored) = stored {
        for id in &stored.items {
            if candidate_ids.contains(id.as_str()) && seen.insert(id.clone()) {
                items.push(id.clone());
            }
        }
    }

    // A hand-numbered legacy filename is not authority, but a unique prefix
    // is useful admission evidence when no first-class priority exists yet.
    // Preserve that relative intent once, then let handoff-order.yaml own it.
    let mut numbered = before
        .iter()
        .filter(|issue| candidate_ids.contains(issue.id.as_str()) && !seen.contains(&issue.id))
        .filter_map(|issue| {
            let (number, _) = prompt_pointer(issue)
                .as_deref()
                .and_then(|path| ordered_name_parts(&issue.id, path))?;
            (number > 0).then_some((number, issue.id.clone()))
        })
        .collect::<Vec<_>>();
    let mut counts = HashMap::new();
    for (number, _) in &numbered {
        *counts.entry(*number).or_insert(0_usize) += 1;
    }
    numbered.retain(|(number, _)| counts[number] == 1);
    numbered.sort_by_key(|(number, _)| *number);
    for (_, id) in numbered {
        if seen.insert(id.clone()) {
            items.push(id);
        }
    }
    for issue in candidates {
        if seen.insert(issue.id.clone()) {
            items.push(issue.id.clone());
        }
    }
    Ok(canonical_order(items))
}

fn ordered_name_parts(issue_id: &str, path: &str) -> Option<(usize, Option<usize>)> {
    let relative = Path::new(path);
    if relative.parent()? != Path::new(HANDOFF_DIR) {
        return None;
    }
    let name = relative.file_name()?.to_str()?;
    let number_end = name.find(['b', '-'])?;
    let number_text = &name[..number_end];
    if number_text.len() < 2 || !number_text.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let number = number_text.parse::<usize>().ok()?;
    let remainder = &name[number_end..];
    let (gate, suffix) = if let Some(gated) = remainder.strip_prefix('b') {
        let gate_end = gated.find('-')?;
        let gate_text = &gated[..gate_end];
        if gate_text.len() < 2 || !gate_text.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        (
            Some(gate_text.parse::<usize>().ok()?),
            &gated[gate_end + 1..],
        )
    } else {
        let suffix = remainder.strip_prefix('-')?;
        (None, suffix)
    };
    suffix
        .strip_prefix(issue_id)
        .is_some_and(|rest| rest.starts_with('-') && rest.ends_with(".md"))
        .then_some((number, gate))
}

fn priority_width(count: usize) -> usize {
    count.to_string().len().max(2)
}

fn ordered_handoff_path(
    issue: &Issue,
    number: usize,
    blocker: Option<usize>,
    width: usize,
) -> String {
    let gate = blocker.map_or_else(String::new, |number| format!("b{number:0width$}"));
    format!(
        "{}/{number:0width$}{}-{}-{}.md",
        HANDOFF_DIR,
        gate,
        issue.id,
        slugify(&issue.title)
    )
}

#[derive(Debug, Clone)]
struct PresentationPlan {
    order: HandoffOrder,
    entries: Vec<HandoffOrderEntry>,
    after: Vec<Issue>,
    renames: Vec<HandoffRename>,
    readme: String,
}

fn assigned_priorities(
    issues_by_id: &HashMap<&str, &Issue>,
    order: &HandoffOrder,
) -> Result<(HashMap<String, usize>, HashSet<String>), String> {
    let count = order.items.len();
    let width = priority_width(count);
    let desired = order
        .items
        .iter()
        .enumerate()
        .map(|(index, id)| (id.as_str(), index + 1))
        .collect::<HashMap<_, _>>();
    let mut assigned = HashMap::new();
    let mut reserved = HashSet::new();
    let mut held_without_number = HashSet::new();

    // A claimed work order is immovable. Its current number wins temporarily
    // and stays reserved until release, even if board priority changed.
    for id in &order.items {
        let issue = issues_by_id
            .get(id.as_str())
            .ok_or_else(|| format!("handoff priority references missing item {}", id))?;
        if !has_live_claim(issue) {
            continue;
        }
        let current = issue
            .prompt
            .as_deref()
            .and_then(|path| ordered_name_parts(&issue.id, path))
            .map(|(number, _)| number)
            .filter(|number| (1..=count).contains(number));
        if let Some(number) = current {
            if !reserved.insert(number) {
                return Err(format!(
                    "claimed handoff priority {:0width$} is occupied more than once",
                    number,
                ));
            }
            assigned.insert(id.clone(), number);
        } else {
            held_without_number.insert(id.clone());
        }
    }

    // Unnumbered claimed work receives its desired slot as a reservation. It
    // remains visibly drifted, but no peer is allowed to take its priority.
    for id in &order.items {
        if !held_without_number.contains(id) {
            continue;
        }
        let preferred = desired[id.as_str()];
        let number = if reserved.insert(preferred) {
            preferred
        } else {
            (1..=count)
                .find(|number| reserved.insert(*number))
                .ok_or_else(|| "no priority remains for a claimed handoff".to_string())?
        };
        assigned.insert(id.clone(), number);
    }

    let mut free = (1..=count)
        .filter(|number| !reserved.contains(number))
        .collect::<Vec<_>>()
        .into_iter();
    for id in &order.items {
        if assigned.contains_key(id) {
            continue;
        }
        assigned.insert(
            id.clone(),
            free.next()
                .ok_or_else(|| "handoff priority assignment is incomplete".to_string())?,
        );
    }
    Ok((assigned, held_without_number))
}

fn render_handoff_index(entries: &[HandoffOrderEntry], issues: &[Issue], width: usize) -> String {
    let by_id = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut rendered = README_PREAMBLE.to_string();
    rendered.push_str("\n## Generated index\n\n");
    rendered.push_str("| Priority | Manna ID | Status | Full blocker list | Handoff |\n");
    rendered.push_str("| ---: | --- | --- | --- | --- |\n");
    for entry in entries {
        let issue = by_id[entry.issue_id.as_str()];
        let blockers = if issue.blocked_by.is_empty() {
            "none".to_string()
        } else {
            issue
                .blocked_by
                .iter()
                .map(|id| format!("`{}`", id))
                .collect::<Vec<_>>()
                .join(", ")
        };
        let handoff = if entry.held_claimed {
            format!(
                "`{}` (held under live claim; expected `{}`)",
                entry.actual_path.as_deref().unwrap_or("missing"),
                entry.expected_path
            )
        } else {
            format!("`{}`", entry.expected_path)
        };
        rendered.push_str(&format!(
            "| {:0width$} | `{}` | {} | {} | {} |\n",
            entry.priority, issue.id, issue.status, blockers, handoff
        ));
    }
    rendered
}

fn build_presentation_plan(
    base: &Path,
    issues: &[Issue],
    stored: Option<&HandoffOrder>,
) -> Result<PresentationPlan, String> {
    let order = normalize_order(issues, stored)?;
    let width = priority_width(order.items.len());
    let issues_by_id = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let (assigned, held_without_number) = assigned_priorities(&issues_by_id, &order)?;

    let mut blocker_numbers = HashMap::new();
    for id in &order.items {
        blocker_numbers.insert(id.as_str(), assigned[id]);
    }

    let mut expected = HashMap::new();
    let mut expected_paths = HashSet::new();
    for id in &order.items {
        let issue = issues_by_id[id.as_str()];
        let mut highest_open = None;
        for blocker_id in &issue.blocked_by {
            let blocker = issues_by_id.get(blocker_id.as_str()).ok_or_else(|| {
                format!(
                    "{} is blocked by {}, which has no numbered authoritative handoff",
                    issue.id, blocker_id
                )
            })?;
            if blocker.status != IssueStatus::Done {
                let number = blocker_numbers.get(blocker_id.as_str()).ok_or_else(|| {
                    format!(
                        "{} is blocked by {}, which has no numbered authoritative handoff",
                        issue.id, blocker_id
                    )
                })?;
                highest_open =
                    Some(highest_open.map_or(*number, |current: usize| current.max(*number)));
            }
        }
        let path = ordered_handoff_path(issue, assigned[id], highest_open, width);
        if !expected_paths.insert(path.clone()) {
            return Err(format!("handoff priority derives duplicate path {}", path));
        }
        expected.insert(id.clone(), path);
    }

    let mut after = issues.to_vec();
    let mut renames = Vec::new();
    let mut entries = Vec::new();
    for id in &order.items {
        let issue = issues_by_id[id.as_str()];
        let actual = issue.prompt.clone();
        let expected_path = expected[id].clone();
        let held_claimed = has_live_claim(issue) && actual.as_deref() != Some(&expected_path);
        if !has_live_claim(issue) && actual.as_deref() != Some(&expected_path) {
            let from = actual.clone().ok_or_else(|| {
                format!(
                    "paired item {} has no authoritative handoff pointer",
                    issue.id
                )
            })?;
            canonical_handoff_path(base, &WorkflowConfig::default(), issue, Some(&from))?;
            canonical_handoff_path(
                base,
                &WorkflowConfig::default(),
                issue,
                Some(&expected_path),
            )?;
            renames.push(HandoffRename {
                issue_id: issue.id.clone(),
                from,
                to: expected_path.clone(),
            });
            let row = after
                .iter_mut()
                .find(|row| row.id == issue.id)
                .expect("ordered item exists in board snapshot");
            row.prompt = Some(expected_path.clone());
        }
        entries.push(HandoffOrderEntry {
            issue_id: issue.id.clone(),
            priority: assigned[id],
            expected_path,
            actual_path: actual,
            held_claimed: held_claimed || held_without_number.contains(id),
        });
    }

    // A completed item is durable history, not launchable work. If it still
    // wears a numbered plan name, return it to the ordinary unnumbered pair
    // path in the same transaction that removes it from priority and index.
    for issue in paired_items(issues)
        .into_iter()
        .filter(|issue| issue.status == IssueStatus::Done)
    {
        let from = issue
            .prompt
            .clone()
            .expect("paired item has an authoritative handoff pointer");
        if ordered_name_parts(&issue.id, &from).is_none() {
            continue;
        }
        let to = canonical_handoff_path(base, &WorkflowConfig::default(), issue, None)?
            .to_string_lossy()
            .into_owned();
        if !expected_paths.insert(to.clone()) {
            return Err(format!(
                "completed handoff derives duplicate historical path {}",
                to
            ));
        }
        canonical_handoff_path(base, &WorkflowConfig::default(), issue, Some(&from))?;
        renames.push(HandoffRename {
            issue_id: issue.id.clone(),
            from,
            to: to.clone(),
        });
        let row = after
            .iter_mut()
            .find(|row| row.id == issue.id)
            .expect("completed paired item exists in board snapshot");
        row.prompt = Some(to);
    }
    entries.sort_by_key(|entry| entry.priority);
    let readme = render_handoff_index(&entries, &after, width);
    Ok(PresentationPlan {
        order,
        entries,
        after,
        renames,
        readme,
    })
}

fn render_presentation_files(
    base: &Path,
    issues: &[Issue],
    stored_text: Option<&str>,
) -> Result<(String, String), String> {
    let stored = stored_text.map(parse_order).transpose()?;
    let order = normalize_order(issues, stored.as_ref())?;
    let order_text = serialize_order(&order)?;
    match build_presentation_plan(base, issues, Some(&order)) {
        Ok(plan) => Ok((order_text, plan.readme)),
        Err(error) => Ok((
            order_text,
            render_unsynchronized_index(&order, issues, &error),
        )),
    }
}

fn render_unsynchronized_index(order: &HandoffOrder, issues: &[Issue], error: &str) -> String {
    let by_id = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut rendered = README_PREAMBLE.to_string();
    rendered.push_str("\n## Generated index\n\n");
    rendered.push_str(&format!(
        "> Launch presentation is blocked: {} No filename in this state is a launch signal. Repair the board and run `agent-do manna sync`.\n\n",
        error.replace(['\n', '|'], " ")
    ));
    rendered.push_str("| Priority | Manna ID | Status | Full blocker list | Current handoff |\n");
    rendered.push_str("| ---: | --- | --- | --- | --- |\n");
    let width = priority_width(order.items.len());
    for (index, id) in order.items.iter().enumerate() {
        let Some(issue) = by_id.get(id.as_str()) else {
            continue;
        };
        let blockers = if issue.blocked_by.is_empty() {
            "none".to_string()
        } else {
            issue
                .blocked_by
                .iter()
                .map(|blocker| format!("`{}`", blocker))
                .collect::<Vec<_>>()
                .join(", ")
        };
        rendered.push_str(&format!(
            "| {:0width$} | `{}` | {} | {} | `{}` |\n",
            index + 1,
            issue.id,
            issue.status,
            blockers,
            issue.prompt.as_deref().unwrap_or("missing")
        ));
    }
    rendered
}

fn split_handoff(text: &str) -> Result<(HandoffFrontmatter, &str), String> {
    let rest = text
        .strip_prefix("---\n")
        .ok_or_else(|| "handoff must begin with YAML frontmatter".to_string())?;
    let boundary = rest
        .find("\n---\n")
        .ok_or_else(|| "handoff frontmatter is not terminated".to_string())?;
    let yaml = &rest[..boundary];
    let body = &rest[boundary + 5..];
    let frontmatter: HandoffFrontmatter = serde_yaml::from_str(yaml)
        .map_err(|error| format!("invalid handoff frontmatter: {}", error))?;
    Ok((frontmatter, body))
}

fn binding_material(text: &str) -> Result<String, String> {
    let rest = text
        .strip_prefix("---\n")
        .ok_or_else(|| "handoff must begin with YAML frontmatter".to_string())?;
    let boundary = rest
        .find("\n---\n")
        .ok_or_else(|| "handoff frontmatter is not terminated".to_string())?;
    let yaml = &rest[..boundary];
    let mut binding_lines = 0;
    let normalized_yaml = yaml
        .lines()
        .map(|line| {
            if line.starts_with("binding:") {
                binding_lines += 1;
                "binding: ''".to_string()
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    if binding_lines != 1 {
        return Err("handoff frontmatter must contain exactly one binding field".to_string());
    }
    Ok(format!(
        "---\n{}\n---\n{}",
        normalized_yaml,
        &rest[boundary + 5..]
    ))
}

fn calculate_binding(text: &str) -> Result<String, String> {
    let material = binding_material(text)?;
    let digest = Sha256::digest(material.as_bytes());
    Ok(format!("sha256:{:x}", digest))
}

pub(crate) fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0_u8, |difference, (left, right)| {
            difference | (left ^ right)
        })
        == 0
}

pub(crate) fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; 32] {
    const BLOCK: usize = 64;
    let mut normalized = [0_u8; BLOCK];
    if key.len() > BLOCK {
        normalized[..32].copy_from_slice(&Sha256::digest(key));
    } else {
        normalized[..key.len()].copy_from_slice(key);
    }
    let mut inner_pad = [0x36_u8; BLOCK];
    let mut outer_pad = [0x5c_u8; BLOCK];
    for index in 0..BLOCK {
        inner_pad[index] ^= normalized[index];
        outer_pad[index] ^= normalized[index];
    }
    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(message);
    let inner_digest = inner.finalize();
    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_digest);
    outer.finalize().into()
}

fn transaction_material(base: &Path, transaction: &PairTransaction) -> Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned).map_err(|error| {
        format!(
            "failed to serialize transaction integrity material: {}",
            error
        )
    })?;
    let mut material = b"agent-do/manna/pair/v2\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn transaction_signature(
    base: &Path,
    key: &[u8],
    transaction: &PairTransaction,
) -> Result<String, String> {
    let digest = hmac_sha256(key, &transaction_material(base, transaction)?);
    let hex = digest
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    Ok(format!("hmac-sha256:{}", hex))
}

fn board_init_path(base: &Path) -> PathBuf {
    base.join(BOARD_INIT_TRANSACTION)
}

fn board_init_material(base: &Path, transaction: &BoardInitTransaction) -> Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned).map_err(|error| {
        format!(
            "failed to serialize board init integrity material: {}",
            error
        )
    })?;
    let mut material = b"agent-do/manna/board-init/v1\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn board_init_signature(
    base: &Path,
    key: &[u8],
    transaction: &BoardInitTransaction,
) -> Result<String, String> {
    let digest = hmac_sha256(key, &board_init_material(base, transaction)?);
    let hex = digest
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    Ok(format!("hmac-sha256:{}", hex))
}

fn legacy_migration_path(base: &Path) -> PathBuf {
    base.join(LEGACY_MIGRATION_TRANSACTION)
}

fn legacy_migration_material(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned).map_err(|error| {
        format!(
            "failed to serialize legacy migration integrity material: {}",
            error
        )
    })?;
    let mut material = b"agent-do/manna/legacy-migration/v1\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn legacy_migration_signature(
    base: &Path,
    key: &[u8],
    transaction: &LegacyBoardTransaction,
) -> Result<String, String> {
    let digest = hmac_sha256(key, &legacy_migration_material(base, transaction)?);
    let hex = digest
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    Ok(format!("hmac-sha256:{}", hex))
}

fn resolve_missing_leaf(path: PathBuf) -> Result<PathBuf, String> {
    let name = path
        .file_name()
        .ok_or_else(|| format!("path has no file name: {}", path.display()))?
        .to_os_string();
    let parent = path
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    let existing = parent
        .ancestors()
        .find(|candidate| candidate.exists())
        .ok_or_else(|| format!("path has no existing ancestor: {}", path.display()))?;
    let canonical = existing
        .canonicalize()
        .map_err(|error| format!("failed to resolve {}: {}", existing.display(), error))?;
    let remainder = parent
        .strip_prefix(existing)
        .map_err(|_| format!("failed to normalize {}", path.display()))?;
    Ok(canonical.join(remainder).join(name))
}

pub(crate) fn recovery_key_path(base: &Path) -> Result<PathBuf, String> {
    let git = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--absolute-git-dir"])
        .output()
        .map_err(|error| format!("failed to locate Git metadata: {}", error))?;
    if git.status.success() {
        let root = String::from_utf8_lossy(&git.stdout).trim().to_string();
        if root.is_empty() {
            return Err("Git returned an empty metadata directory".to_string());
        }
        return resolve_missing_leaf(
            PathBuf::from(root)
                .join("agent-do")
                .join("manna-recovery.key"),
        );
    }

    let home = std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".agent-do")))
        .ok_or_else(|| {
            "cannot protect Manna recovery journals outside Git without AGENT_DO_HOME or HOME"
                .to_string()
        })?;
    let canonical = base
        .canonicalize()
        .map_err(|error| format!("failed to resolve project root: {}", error))?;
    let project = Sha256::digest(canonical.to_string_lossy().as_bytes());
    resolve_missing_leaf(
        home.join("manna")
            .join("recovery-keys")
            .join(format!("{:x}.key", project)),
    )
}

pub(crate) fn reject_symlink_components(path: &Path, label: &str) -> Result<(), String> {
    let mut cursor = PathBuf::new();
    for component in path.components() {
        cursor.push(component.as_os_str());
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "refusing {} through symlink {}",
                    label,
                    cursor.display()
                ))
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(error) => return Err(format!("failed to inspect {}: {}", cursor.display(), error)),
        }
    }
    Ok(())
}

fn read_private_key(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    reject_symlink_components(path, label)?;
    let mut key = Vec::new();
    File::open(path)
        .and_then(|mut file| file.read_to_end(&mut key))
        .map_err(|error| format!("failed to read {} {}: {}", label, path.display(), error))?;
    if key.len() != 32 {
        return Err(format!(
            "{} {} has invalid length {}; expected 32 bytes",
            label,
            path.display(),
            key.len()
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(path)
            .map_err(|error| format!("failed to inspect {}: {}", label, error))?
            .permissions()
            .mode();
        if mode & 0o077 != 0 {
            return Err(format!(
                "{} {} must not be readable by group or others",
                label,
                path.display()
            ));
        }
    }
    Ok(key)
}

pub(crate) fn load_private_key(path: &Path, create: bool, label: &str) -> Result<Vec<u8>, String> {
    if path.is_file() {
        return read_private_key(path, label);
    }
    if path_exists(path) {
        return Err(format!(
            "{} path is not a regular file: {}",
            label,
            path.display()
        ));
    }
    if !create {
        return Err(format!("{} {} is missing", label, path.display()));
    }
    let parent = path
        .parent()
        .ok_or_else(|| format!("{} has no parent: {}", label, path.display()))?;
    reject_symlink_components(parent, &format!("{} directory", label))?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create {}: {}", parent.display(), error))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
            .map_err(|error| format!("failed to protect {}: {}", parent.display(), error))?;
    }

    let mut key = [0_u8; 32];
    OsRng.fill_bytes(&mut key);
    let mut nonce = [0_u8; 16];
    OsRng.fill_bytes(&mut nonce);
    let nonce = nonce
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    let temp = parent.join(format!(".manna-key.{}.{}.tmp", std::process::id(), nonce));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&temp)
        .map_err(|error| format!("failed to create {}: {}", temp.display(), error))?;
    if let Err(error) = file.write_all(&key).and_then(|_| file.sync_all()) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to write {}: {}", temp.display(), error));
    }
    drop(file);
    match fs::hard_link(&temp, path) {
        Ok(()) => {
            fs::remove_file(&temp)
                .map_err(|error| format!("failed to remove {}: {}", temp.display(), error))?;
            sync_parent(path)?;
            Ok(key.to_vec())
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let _ = fs::remove_file(&temp);
            read_private_key(path, label)
        }
        Err(error) => {
            let _ = fs::remove_file(&temp);
            Err(format!(
                "failed to install {} {}: {}",
                label,
                path.display(),
                error
            ))
        }
    }
}

fn load_recovery_key(base: &Path, create: bool) -> Result<Vec<u8>, String> {
    let path = recovery_key_path(base)?;
    load_private_key(&path, create, "Manna recovery key").map_err(|error| {
        if !create && error.ends_with(" is missing") {
            format!(
                "pending Manna transaction cannot be authenticated because {}",
                error
            )
        } else {
            error
        }
    })
}

fn session_identity_key_path() -> Result<PathBuf, String> {
    let home = std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".agent-do")))
        .ok_or_else(|| {
            "cannot derive host session ownership without AGENT_DO_HOME or HOME".to_string()
        })?;
    resolve_missing_leaf(home.join("manna").join("session-identity.key"))
}

fn compact_runtime_id(value: &str) -> String {
    value
        .chars()
        .filter(|character| character.is_ascii_alphanumeric())
        .flat_map(char::to_lowercase)
        .take(16)
        .collect()
}

pub fn runtime_session_label(runtime: &str, opaque_id: &str) -> Result<String, String> {
    let compact = compact_runtime_id(opaque_id);
    if compact.is_empty() {
        return Err(format!(
            "{} session identity is empty after normalization",
            runtime
        ));
    }
    Ok(format!("{}-{}", runtime, compact))
}

/// Derive an authenticated Manna identity from an opaque host-owned session
/// identifier. The public label matches agent-do coord, while the ownership
/// proof is an HMAC under a machine-local key outside the repository. Knowing
/// the visible label is therefore insufficient to forge lifecycle authority.
pub fn runtime_session_identity(runtime: &str, opaque_id: &str) -> Result<SessionIdentity, String> {
    let label = runtime_session_label(runtime, opaque_id)?;
    let key_path = session_identity_key_path()?;
    let key = load_private_key(&key_path, true, "Manna session identity key")?;
    let material = format!("agent-do/manna/session/v1\0{}\0{}", runtime, opaque_id);
    let proof = hmac_sha256(&key, material.as_bytes())
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    SessionIdentity::from_token(&label, &proof)
}

fn render_document(frontmatter: &HandoffFrontmatter, body: &str) -> Result<String, String> {
    let mut unsigned = frontmatter.clone();
    unsigned.binding.clear();
    let yaml = serde_yaml::to_string(&unsigned)
        .map_err(|error| format!("failed to serialize handoff frontmatter: {}", error))?;
    let unsigned_document = format!("---\n{}---\n{}", yaml, body);
    let binding = calculate_binding(&unsigned_document)?;
    let mut signed = frontmatter.clone();
    signed.binding = binding;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize handoff frontmatter: {}", error))?;
    Ok(format!("---\n{}---\n{}", yaml, body))
}

fn generated_body(issue: &Issue) -> String {
    if issue.issue_type == IssueType::Track {
        return generated_track_body(issue);
    }
    let work_order = issue
        .description
        .as_deref()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .unwrap_or(&issue.title);
    let inputs = if let Some(source) = issue.source.as_deref() {
        format!("- {}", source)
    } else {
        "- None declared.".to_string()
    };
    format!(
        "\n# Handoff: {}\n\nBoard state is canonical in `.manna/`. This file is the work order for one item only.\n\n## Claim\n\n```bash\nagent-do manna claim {}\n```\n\n## Scope\n\n{}\n\n## Inputs\n\n{}\n\n## Work order\n\n{}\n\n## Completion\n\n1. Produce the scoped deliverables and verification receipts.\n2. Update this handoff only when continuation context changed.\n3. Seal changes with `agent-do manna handoff seal {}`.\n4. Commit with `Manna: {}` and run `agent-do manna done {}` only after the work is verified.\n",
        issue.title,
        issue.id,
        issue.title,
        inputs,
        work_order,
        issue.id,
        issue.id,
        issue.id
    )
}

/// The dispatch work order for a track. The same five required sections as an
/// item handoff, so one validator and one claim gate serve both; the body is
/// the protocol a single agent follows to work the track's items in
/// dependency order. It names live board commands and carries no ledger: the
/// board is the only record of progress, and a successor rebuilds from it.
fn generated_track_body(issue: &Issue) -> String {
    let description = issue
        .description
        .as_deref()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .unwrap_or(&issue.title);
    let inputs = if let Some(source) = issue.source.as_deref() {
        format!("- {}", source)
    } else {
        "- None declared.".to_string()
    };
    let id = &issue.id;
    format!(
        "\n# Handoff: {title}\n\n\
Board state is canonical in `.manna/`. This file is the work order for one track: one agent works the track's items in dependency order, one claim at a time. It is not a claim on the items, a progress ledger, or coordinator authority.\n\n\
## Claim\n\n```bash\nagent-do manna claim {id}\n```\n\n\
## Scope\n\n{title}\n\n\
## Inputs\n\n{inputs}\n\n\
## Work order\n\n{description}\n\n\
**Track dispatch protocol.** Every item in this track keeps its own claim, its own sealed work order, and its own close. The steps below are the whole assignment.\n\n\
1. Read the track from the canonical board: `agent-do manna show {id} --json`. `children.next` names the one item to claim now: open, unclaimed, every blocker done, highest handoff priority first (`.manna/handoff-order.yaml`), then the oldest row, then the lowest id. `children.eligible` lists the rest in that order; `children.held`, `children.waiting`, and `children.decisions` say what is not yours to take; `children.stall` says why `next` is null.\n\
2. Claim that item individually: `agent-do manna claim <item-id>`. A refusal (claimed elsewhere, blocked, a changed or unsealed work order) is final for that item: take the next eligible item instead. Never retry around a refusal, never claim through another identity, and never work an item you do not hold.\n\
3. Read the item's sealed handoff named by its `prompt` field and follow it to completion exactly as a single-item worker would: its owned paths, its verification receipts, a Conventional Commit carrying `Manna: <item-id>`, and its own close. `agent-do manna done <item-id>` closes an ordinary item; a managed item takes `agent-do manna submit` instead, and a submission is not acceptance: the item stays in progress until its coordinator accepts it.\n\
4. Refresh before every selection by running step 1 again. The board is the only record of progress. Items added to the track since your claim are listed under `children.added_since_claim`: each carries its own sealed work order, so name the change of scope in your report before claiming one; nothing is claimed silently. Items moved out of the track or deleted disappear from the list; one you already hold stays yours under its own work order.\n\
5. Continue while `children.next` is non-null. When it is null and `children.open` is not zero, record the exact blocker (`children.stall`, the item ids, the owner of a claim held elsewhere, the external prerequisite) in your report and in this handoff's receipts, reseal, and stop. A lane that ends releases the track with `agent-do manna abandon {id}`; every item claim and every commit stays where it is, and a successor claims the track and rebuilds progress from the board, never from this file.\n\
6. Holding this track grants only the right to claim its eligible items one at a time. It reserves no item, blocks no independent worker (any session may claim this track's items at any time; the board's atomic claim decides), confers no coordinator authority, accepts nothing, and authorizes no merge, deploy, push, or pull request.\n\n\
## Completion\n\n\
1. `agent-do manna done {id}` closes the track only when every item in it is done; the board refuses otherwise and lists what is open. Submitted-but-unaccepted items are open. An empty track cannot close; delete it or give it items.\n\
2. Update this handoff only when continuation context changed; seal with `agent-do manna handoff seal {id}`.\n\
3. Commit board paperwork with `Manna: {id}` only on a commit that advances the track itself; item work carries the item's own trailer.\n",
        title = issue.title,
        id = id,
        inputs = inputs,
        description = description,
    )
}

fn adopted_body(issue: &Issue, legacy: &str, provenance: &str) -> String {
    let inputs = if let Some(source) = issue.source.as_deref() {
        format!("- {}", source)
    } else {
        "- None declared.".to_string()
    };
    let provenance = serde_json::to_string(provenance)
        .expect("serializing a legacy pointer as a JSON string cannot fail");
    format!(
        "\n# Handoff: {}\n\nBoard state is canonical in `.manna/`. This file is the work order for one item only.\n\n## Claim\n\n```bash\nagent-do manna claim {}\n```\n\n## Scope\n\n{}\n\n## Inputs\n\n{}\n\n## Work order\n\n> Legacy migration source: {}\n\n{}\n\n## Completion\n\n1. Produce the scoped deliverables and verification receipts.\n2. Update this handoff only when continuation context changed.\n3. Seal changes with `agent-do manna handoff seal {}`.\n4. Commit with `Manna: {}` and run `agent-do manna done {}` only after the work is verified.\n",
        issue.title,
        issue.id,
        issue.title,
        inputs,
        provenance,
        legacy,
        issue.id,
        issue.id,
        issue.id
    )
}

fn frontmatter_for(base: &Path, issue: &Issue) -> HandoffFrontmatter {
    HandoffFrontmatter {
        workflow: WORKFLOW_VERSION,
        manna: issue.id.clone(),
        track: issue.track.clone(),
        source: issue.source.clone(),
        base_commit: current_base_commit(base),
        scope: issue.title.clone(),
        inputs: issue.source.iter().cloned().collect(),
        binding: String::new(),
    }
}

pub fn render_handoff(base: &Path, issue: &Issue) -> Result<String, String> {
    render_document(&frontmatter_for(base, issue), &generated_body(issue))
}

fn render_adopted_handoff(
    base: &Path,
    issue: &Issue,
    legacy: &str,
    provenance: &str,
) -> Result<String, String> {
    render_document(
        &frontmatter_for(base, issue),
        &adopted_body(issue, legacy, provenance),
    )
}

fn append_adopted_source(document: &str, legacy: &str, provenance: &str) -> Result<String, String> {
    let (frontmatter, body) = split_handoff(document)?;
    let positions = required_section_positions(body)?;
    let completion = positions[4];
    let provenance = serde_json::to_string(provenance)
        .expect("serializing a legacy pointer as a JSON string cannot fail");
    let repaired = format!(
        "{}> Legacy migration source: {}\n\n{}\n\n{}",
        &body[..completion],
        provenance,
        legacy,
        &body[completion..]
    );
    render_document(&frontmatter, &repaired)
}

fn required_section_positions(body: &str) -> Result<Vec<usize>, String> {
    let mut positions = Vec::new();
    let mut search_from = 0;
    for section in ["## Claim", "## Scope", "## Inputs", "## Work order"] {
        let needle = format!("{}\n", section);
        let relative = body[search_from..]
            .find(&needle)
            .ok_or_else(|| format!("handoff is missing required section {}", section))?;
        let position = search_from + relative;
        positions.push(position);
        search_from = position + needle.len();
    }
    let completion = body
        .rfind("## Completion\n")
        .filter(|position| *position >= search_from)
        .ok_or_else(|| "handoff is missing required section ## Completion".to_string())?;
    positions.push(completion);
    Ok(positions)
}

fn validate_document(issue: &Issue, text: &str) -> Result<String, String> {
    let (frontmatter, body) = split_handoff(text)?;
    if frontmatter.workflow != WORKFLOW_VERSION {
        return Err(format!(
            "handoff workflow version {} is not current {}",
            frontmatter.workflow, WORKFLOW_VERSION
        ));
    }
    if frontmatter.manna != issue.id {
        return Err(format!(
            "handoff frontmatter points to {}, expected {}",
            frontmatter.manna, issue.id
        ));
    }
    if frontmatter.track != issue.track {
        return Err("handoff track does not match the Manna item".to_string());
    }
    if frontmatter.source != issue.source {
        return Err("handoff source does not match the Manna item".to_string());
    }
    if frontmatter.inputs != issue.source.iter().cloned().collect::<Vec<_>>() {
        return Err("handoff inputs do not match the Manna item source".to_string());
    }
    if frontmatter.scope != issue.title {
        return Err("handoff scope does not match the Manna item title".to_string());
    }
    if frontmatter.base_commit.trim().is_empty() {
        return Err("handoff base_commit cannot be empty".to_string());
    }
    let sections = required_section_positions(body)?;
    let claim_heading = "## Claim\n";
    let claim_body = body[sections[0] + claim_heading.len()..sections[1]].trim();
    let expected_claim = format!("```bash\nagent-do manna claim {}\n```", issue.id);
    if claim_body != expected_claim {
        return Err(format!(
            "handoff Claim section must contain exactly `agent-do manna claim {}`",
            issue.id
        ));
    }
    let calculated = calculate_binding(text)?;
    if frontmatter.binding != calculated {
        return Err(format!(
            "handoff content binding is stale: frontmatter {}, calculated {}",
            frontmatter.binding, calculated
        ));
    }
    match issue.handoff_digest.as_deref() {
        Some(binding) if binding == calculated => Ok(calculated),
        Some(binding) => Err(format!(
            "Manna item binding {} does not match handoff {}",
            binding, calculated
        )),
        None => Err(format!("{} has no authoritative handoff binding", issue.id)),
    }
}

fn transaction_path(base: &Path, issue_id: &str) -> PathBuf {
    base.join(TRANSACTION_DIR)
        .join(format!("{}.yaml", issue_id))
}

fn same_lifecycle(before: &Issue, after: &Issue) -> bool {
    before.id == after.id
        && before.created_at == after.created_at
        && before.status == after.status
        && before.blocked_by == after.blocked_by
        && before.claimed_by == after.claimed_by
        && before.claimed_at == after.claimed_at
        && before.claim_token_hash == after.claim_token_hash
}

fn validate_legacy_migration_transaction(
    base: &Path,
    path: &Path,
    transaction: &LegacyBoardTransaction,
    key: &[u8],
) -> Result<WorkflowConfig, String> {
    if transaction.version != LEGACY_MIGRATION_VERSION {
        return Err(format!(
            "unsupported legacy migration transaction version {}",
            transaction.version
        ));
    }
    let expected_path = legacy_migration_path(base);
    if path != expected_path {
        return Err(format!(
            "legacy migration transaction path {} is not {}",
            path.display(),
            expected_path.display()
        ));
    }
    let expected_signature = legacy_migration_signature(base, key, transaction)?;
    if !constant_time_eq(
        transaction.integrity.as_bytes(),
        expected_signature.as_bytes(),
    ) {
        return Err(format!(
            "legacy migration transaction {} failed HMAC authentication",
            path.display()
        ));
    }
    if transaction.before.len() != transaction.after.len() {
        return Err("legacy migration cannot add or delete board rows".to_string());
    }
    let mut row_ids = HashSet::new();
    let mut annotated_pointer_repairs = HashSet::new();
    for (before, after) in transaction.before.iter().zip(&transaction.after) {
        if before.id != after.id || !row_ids.insert(after.id.clone()) {
            return Err(
                "legacy migration must preserve one unique row for every issue id".to_string(),
            );
        }
        after
            .validate()
            .map_err(|error| format!("invalid migrated row {}: {}", after.id, error))?;
        let pass_through = before.handoff_digest.is_some() || before.legacy_migration.is_some();
        let pointer_repair = annotated_pointer_repair_matches(base, before, after)?;
        if pass_through {
            if before != after && !pointer_repair {
                return Err(format!(
                    "legacy migration changed already-admitted row {}",
                    after.id
                ));
            }
            if pointer_repair {
                annotated_pointer_repairs.insert(after.id.clone());
            }
            if before.handoff_digest.is_none() && !migration_annotation_matches(before) {
                return Err(format!(
                    "legacy migration annotation on {} is incomplete or inconsistent",
                    before.id
                ));
            }
        } else if !migration_annotation_matches(after) {
            return Err(format!(
                "migrated row {} has no consistent legacy migration annotation",
                after.id
            ));
        }
    }

    let board: BoardConfig = serde_yaml::from_str(&transaction.board_after)
        .map_err(|error| format!("invalid migrated board identity: {}", error))?;
    if board.version != 1
        || board.workflow != BoardMode::Strict
        || board.migrated_from_legacy_at.is_none()
    {
        return Err(
            "legacy migration must publish a strict, migration-stamped board identity".to_string(),
        );
    }
    let config: WorkflowConfig = serde_yaml::from_str(&transaction.workflow_after)
        .map_err(|error| format!("invalid migrated workflow config: {}", error))?;
    config.validate()?;
    if let Some(order_after) = transaction.order_after.as_deref() {
        let order = parse_order(order_after)?;
        if serialize_order(&order)? != order_after {
            return Err("legacy migration handoff priority is not canonical YAML".to_string());
        }
        let (_, expected_readme) =
            render_presentation_files(base, &transaction.after, Some(order_after))?;
        if transaction.readme_after != expected_readme {
            return Err("legacy migration README is not the canonical generated index".to_string());
        }
    }
    let expected_gitignore =
        workflow_gitignore_content(transaction.gitignore_before.as_deref().unwrap_or_default());
    if transaction.gitignore_after != expected_gitignore {
        return Err("legacy migration Git visibility update is not canonical".to_string());
    }

    let rows = transaction
        .after
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let original_rows = transaction
        .before
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut document_ids = HashSet::new();
    let mut document_paths = HashSet::new();
    for migration_document in &transaction.documents {
        if !document_ids.insert(migration_document.issue_id.clone()) {
            return Err(format!(
                "legacy migration carries duplicate handoff documents for {}",
                migration_document.issue_id
            ));
        }
        let issue = rows
            .get(migration_document.issue_id.as_str())
            .ok_or_else(|| {
                format!(
                    "legacy migration handoff targets missing issue {}",
                    migration_document.issue_id
                )
            })?;
        let original = original_rows[migration_document.issue_id.as_str()];
        let strict_pass_through = original.handoff_digest.is_some();
        let pointer_repair = annotated_pointer_repairs.contains(&migration_document.issue_id);
        let migrated_pair = !strict_pass_through
            && issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Paired
            });
        if issue.issue_type != IssueType::Item || (!strict_pass_through && !migrated_pair) {
            return Err(format!(
                "legacy migration handoff {} does not target a strict or newly paired item",
                migration_document.issue_id
            ));
        }
        if strict_pass_through
            && !pointer_repair
            && migration_document.previous_document.as_deref()
                != Some(migration_document.document.as_str())
        {
            return Err(format!(
                "strict handoff {} must preserve its exact existing bytes",
                migration_document.issue_id
            ));
        }
        if strict_pass_through && !pointer_repair && migration_document.source_document.is_some() {
            return Err(format!(
                "strict handoff {} cannot carry a legacy source document",
                migration_document.issue_id
            ));
        }
        if pointer_repair {
            let previous = migration_document
                .previous_document
                .as_deref()
                .ok_or_else(|| {
                    format!(
                        "annotated pointer repair {} has no previous handoff bytes",
                        migration_document.issue_id
                    )
                })?;
            validate_document(original, previous).map_err(|error| {
                format!(
                    "annotated pointer repair {} does not start from its sealed handoff: {}",
                    migration_document.issue_id, error
                )
            })?;
            let source = migration_document
                .source_document
                .as_deref()
                .ok_or_else(|| {
                    format!(
                        "annotated pointer repair {} has no source bytes",
                        migration_document.issue_id
                    )
                })?;
            let provenance = issue
                .legacy_migration
                .as_ref()
                .and_then(|migration| migration.previous_prompt.as_deref())
                .ok_or_else(|| {
                    format!(
                        "annotated pointer repair {} has no normalized provenance",
                        migration_document.issue_id
                    )
                })?;
            let expected = append_adopted_source(previous, source, provenance)?;
            if migration_document.document != expected {
                return Err(format!(
                    "annotated pointer repair {} is not the canonical content-preserving rebind",
                    migration_document.issue_id
                ));
            }
        }
        if migrated_pair
            && migration_document.previous_document.is_some()
            && migration_document.previous_document != migration_document.source_document
        {
            return Err(format!(
                "adopted handoff {} would replace target bytes it did not import",
                migration_document.issue_id
            ));
        }
        if let Some(source) = migration_document.source_document.as_deref() {
            if !migration_document.document.contains(source) {
                return Err(format!(
                    "adopted handoff {} does not preserve its legacy work-order content",
                    migration_document.issue_id
                ));
            }
        }
        let canonical = canonical_handoff_path(base, &config, issue, issue.prompt.as_deref())?;
        let supplied = normalize_relative(Path::new(&migration_document.handoff))?;
        if !document_paths.insert(supplied.clone()) {
            return Err(format!(
                "legacy migration carries duplicate handoff target {}",
                supplied.display()
            ));
        }
        if supplied != canonical {
            return Err(format!(
                "legacy migration handoff {} is not authoritative path {}",
                supplied.display(),
                canonical.display()
            ));
        }
        validate_document(issue, &migration_document.document)?;
    }

    let documents_by_id = transaction
        .documents
        .iter()
        .map(|document| (document.issue_id.as_str(), document))
        .collect::<HashMap<_, _>>();
    let mut archive_sources = HashSet::new();
    let mut archive_targets = HashSet::new();
    let mut archived_issue_ids = HashSet::new();
    for source_archive in &transaction.source_archives {
        let source = safe_relative_path(base, Path::new(&source_archive.source), true)?;
        if source.starts_with(HANDOFF_DIR) || path_contains_git_metadata(&source) {
            return Err(format!(
                "legacy source archive has an invalid source path: {}",
                source.display()
            ));
        }
        let archive = safe_relative_path(base, Path::new(&source_archive.archive), true)?;
        if !archive.starts_with(LEGACY_SOURCE_ARCHIVE_DIR)
            || archive.extension().and_then(|extension| extension.to_str()) != Some("source")
            || archive != legacy_source_archive_path(&source)
        {
            return Err(format!(
                "legacy source archive has a non-canonical target: {}",
                archive.display()
            ));
        }
        if !archive_sources.insert(source.clone()) || !archive_targets.insert(archive) {
            return Err(format!(
                "legacy migration carries a duplicate source archive for {}",
                source.display()
            ));
        }
        let mut canonical_issue_ids = source_archive.issue_ids.clone();
        canonical_issue_ids.sort();
        canonical_issue_ids.dedup();
        if canonical_issue_ids.is_empty() || canonical_issue_ids != source_archive.issue_ids {
            return Err(format!(
                "legacy source archive {} has a non-canonical issue set",
                source.display()
            ));
        }
        for issue_id in &source_archive.issue_ids {
            if !archived_issue_ids.insert(issue_id.clone()) {
                return Err(format!(
                    "legacy migration links {} to more than one source archive",
                    issue_id
                ));
            }
            let issue = rows.get(issue_id.as_str()).ok_or_else(|| {
                format!(
                    "legacy source archive {} targets missing issue {}",
                    source.display(),
                    issue_id
                )
            })?;
            let annotation = issue.legacy_migration.as_ref().ok_or_else(|| {
                format!(
                    "legacy source archive targets unannotated issue {}",
                    issue_id
                )
            })?;
            if annotation.disposition != LegacyMigrationDisposition::Paired
                || annotation.previous_prompt.as_deref() != Some(source_archive.source.as_str())
            {
                return Err(format!(
                    "legacy source archive {} does not match provenance on {}",
                    source.display(),
                    issue_id
                ));
            }
            let document = documents_by_id.get(issue_id.as_str()).ok_or_else(|| {
                format!("legacy source archive targets missing handoff {}", issue_id)
            })?;
            if !document.document.contains(&source_archive.document) {
                return Err(format!(
                    "canonical handoff {} does not preserve archived source {}",
                    document.handoff,
                    source.display()
                ));
            }
            if document
                .source_document
                .as_deref()
                .is_some_and(|source| source != source_archive.document)
            {
                return Err(format!(
                    "legacy source archive bytes do not match imported source for {}",
                    issue_id
                ));
            }
        }
    }
    for migration_document in &transaction.documents {
        if migration_document.source_document.is_none() {
            continue;
        }
        let issue = rows[migration_document.issue_id.as_str()];
        if local_legacy_source(issue, base)?.is_some()
            && !archived_issue_ids.contains(&migration_document.issue_id)
        {
            return Err(format!(
                "imported local source for {} is not retired by the migration transaction",
                migration_document.issue_id
            ));
        }
    }
    for (original, issue) in transaction.before.iter().zip(&transaction.after) {
        let requires_document = original.handoff_digest.is_some()
            || issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Paired
            });
        if requires_document != document_ids.contains(&issue.id) {
            return Err(format!(
                "legacy migration document set does not match active item {}",
                issue.id
            ));
        }
    }
    Ok(config)
}

fn validate_handoff_sync_transaction(
    base: &Path,
    transaction: &PairTransaction,
) -> Result<(), String> {
    if transaction.issue_id != HANDOFF_SYNC_TRANSACTION_ID
        || transaction.before.is_some()
        || transaction.after.is_some()
        || transaction.handoff != HANDOFF_DIR
        || transaction.archive.is_some()
        || transaction.document.is_some()
    {
        return Err("rename transaction has an invalid top-level shape".to_string());
    }
    let sync = transaction
        .sync
        .as_ref()
        .ok_or_else(|| "rename transaction has no sync payload".to_string())?;
    if sync.order_before.is_none() || sync.readme_before.is_none() {
        return Err(
            "rename transaction requires authenticated priority and README before states"
                .to_string(),
        );
    }
    if sync.before.len() != sync.after.len() {
        return Err("handoff sync cannot add or delete board rows".to_string());
    }
    let mut ids = HashSet::new();
    for (before, after) in sync.before.iter().zip(&sync.after) {
        if before.id != after.id || !ids.insert(before.id.clone()) {
            return Err("handoff sync must preserve one unique row for every issue id".to_string());
        }
        after
            .validate()
            .map_err(|error| format!("invalid synchronized row {}: {}", after.id, error))?;
        let mut expected = before.clone();
        expected.prompt = after.prompt.clone();
        if &expected != after {
            return Err(format!(
                "handoff sync may change only the prompt pointer for {}",
                before.id
            ));
        }
    }

    if let Some(before) = sync.order_before.as_deref() {
        parse_order(before)?;
    }
    let order = parse_order(&sync.order_after)?;
    if serialize_order(&order)? != sync.order_after {
        return Err("handoff sync priority state is not canonical YAML".to_string());
    }
    let expected = build_presentation_plan(base, &sync.before, Some(&order))?;
    if expected.order != order
        || expected.after != sync.after
        || expected.renames != sync.renames
        || expected.readme != sync.readme_after
    {
        return Err("handoff sync payload is not derived from its board priority".to_string());
    }
    Ok(())
}

fn validate_transaction(
    base: &Path,
    config: &WorkflowConfig,
    path: &Path,
    transaction: &PairTransaction,
    key: &[u8],
) -> Result<(), String> {
    if transaction.version != WORKFLOW_VERSION {
        return Err(format!(
            "unsupported pair transaction version {}",
            transaction.version
        ));
    }
    let expected_path = transaction_path(base, &transaction.issue_id);
    if path != expected_path {
        return Err(format!(
            "transaction filename {} does not match authenticated issue {}",
            path.display(),
            transaction.issue_id
        ));
    }
    let expected_signature = transaction_signature(base, key, transaction)?;
    if !constant_time_eq(
        transaction.integrity.as_bytes(),
        expected_signature.as_bytes(),
    ) {
        return Err(format!(
            "transaction {} failed HMAC authentication",
            path.display()
        ));
    }
    if transaction.action == PairAction::Rename {
        return validate_handoff_sync_transaction(base, transaction);
    }
    if transaction.sync.is_some() {
        return Err("non-rename pair transaction carries a sync payload".to_string());
    }
    for row in [&transaction.before, &transaction.after]
        .into_iter()
        .flatten()
    {
        row.validate()
            .map_err(|error| format!("invalid transaction row {}: {}", row.id, error))?;
        if row.id != transaction.issue_id {
            return Err(format!(
                "transaction issue {} contains row {}",
                transaction.issue_id, row.id
            ));
        }
    }

    let (path_issue, document_expected, archive_expected) = match transaction.action {
        PairAction::Create => {
            if transaction.before.is_some()
                || transaction.after.is_none()
                || transaction.document.is_none()
                || transaction.archive.is_some()
                || !pairable(transaction.after.as_ref().unwrap().issue_type)
            {
                return Err("create transaction has an invalid shape".to_string());
            }
            (transaction.after.as_ref().unwrap(), true, false)
        }
        PairAction::Attach => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("attach transaction is missing a board row".to_string());
            };
            // Attach gives a row its first pair: a dream becoming an item or a
            // track, or a container track receiving its dispatch work order.
            if transaction.document.is_none()
                || transaction.archive.is_some()
                || before.prompt.is_some()
                || before.handoff_digest.is_some()
                || !pairable(after.issue_type)
                || !same_lifecycle(before, after)
            {
                return Err(
                    "attach transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (after, true, false)
        }
        PairAction::Rebind => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("rebind transaction is missing a board row".to_string());
            };
            if transaction.document.is_none()
                || transaction.archive.is_some()
                || !pairable(before.issue_type)
                || !pairable(after.issue_type)
                || before.prompt != after.prompt
                || !same_lifecycle(before, after)
            {
                return Err(
                    "rebind transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (after, true, false)
        }
        PairAction::Rename => unreachable!("rename transactions return above"),
        PairAction::Detach => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("detach transaction is missing a board row".to_string());
            };
            if transaction.document.is_some()
                || transaction.archive.is_none()
                || !pairable(before.issue_type)
                || pairable(after.issue_type)
                || after.prompt.is_some()
                || after.handoff_digest.is_some()
                || !same_lifecycle(before, after)
            {
                return Err(
                    "detach transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (before, false, true)
        }
        PairAction::Delete => {
            let Some(before) = transaction.before.as_ref() else {
                return Err("delete transaction has no before row".to_string());
            };
            if transaction.after.is_some()
                || transaction.document.is_some()
                || transaction.archive.is_none()
                || !pairable(before.issue_type)
            {
                return Err("delete transaction has an invalid shape".to_string());
            }
            (before, false, true)
        }
    };

    let canonical = canonical_handoff_path(base, config, path_issue, path_issue.prompt.as_deref())?;
    let supplied = normalize_relative(Path::new(&transaction.handoff))?;
    if supplied != canonical {
        return Err(format!(
            "transaction handoff {} is not the authoritative path {}",
            supplied.display(),
            canonical.display()
        ));
    }
    if document_expected {
        let after = transaction.after.as_ref().unwrap();
        let document = transaction.document.as_deref().unwrap();
        validate_document(after, document)?;
    }
    if archive_expected {
        let before = transaction.before.as_ref().unwrap();
        let expected = archive_path(before);
        let actual = normalize_relative(Path::new(transaction.archive.as_deref().unwrap()))?;
        if actual != expected {
            return Err(format!(
                "transaction archive {} is not the authoritative path {}",
                actual.display(),
                expected.display()
            ));
        }
    }
    Ok(())
}

fn write_transaction(
    base: &Path,
    config: &WorkflowConfig,
    transaction: &PairTransaction,
) -> Result<PathBuf, String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = transaction_path(base, &transaction.issue_id);
    let key = load_recovery_key(base, true)?;
    let mut signed = transaction.clone();
    signed.integrity = transaction_signature(base, &key, &signed)?;
    validate_transaction(base, config, &path, &signed, &key)?;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize pair transaction: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false).map_err(|error| {
        format!(
            "{}; pending Manna pair transaction already exists for {}; run `agent-do manna init`",
            error, transaction.issue_id
        )
    })?;
    Ok(path)
}

fn remove_transaction_if_unchanged(
    path: &Path,
    opened_metadata: &fs::Metadata,
    opened_text: &str,
) -> Result<(), String> {
    reject_symlink(path, "transaction")?;
    let current_metadata = match fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(format!("failed to recheck {}: {}", path.display(), error)),
    };
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if opened_metadata.dev() != current_metadata.dev()
            || opened_metadata.ino() != current_metadata.ino()
        {
            return Err(format!(
                "transaction {} changed during recovery and was left in place",
                path.display()
            ));
        }
    }
    let current = fs::read_to_string(path)
        .map_err(|error| format!("failed to recheck {}: {}", path.display(), error))?;
    if current != opened_text {
        return Err(format!(
            "transaction {} changed during recovery and was left in place",
            path.display()
        ));
    }
    fs::remove_file(path)
        .map_err(|error| format!("failed to remove {}: {}", path.display(), error))?;
    sync_parent(path)
}

fn install_transaction_document(
    base: &Path,
    relative: &Path,
    document: &str,
) -> Result<(), String> {
    let relative = safe_relative_path(base, relative, true)?;
    if !relative.starts_with(HANDOFF_DIR)
        || relative.starts_with(HANDOFF_ARCHIVE_DIR)
        || relative
            .extension()
            .and_then(|extension| extension.to_str())
            != Some("md")
    {
        return Err("transaction document target is outside canonical .handoff/".to_string());
    }
    let parent = relative
        .parent()
        .ok_or_else(|| format!("handoff has no parent: {}", relative.display()))?;
    safe_create_dir_all(base, parent)?;
    let target = base.join(&relative);
    if target.is_file() {
        let existing = fs::read_to_string(&target)
            .map_err(|error| format!("failed to read {}: {}", target.display(), error))?;
        if existing == document {
            return Ok(());
        }
    }
    atomic_write_replace(&target, document)
}

fn check_managed_text_state(
    path: &Path,
    before: Option<&str>,
    after: &str,
    label: &str,
) -> Result<(), String> {
    let current = read_optional_text(path, label)?;
    if current.as_deref() != before && current.as_deref() != Some(after) {
        return Err(format!(
            "{} changed after the workflow transaction was prepared: {}",
            label,
            path.display()
        ));
    }
    Ok(())
}

fn install_managed_text(
    path: &Path,
    before: Option<&str>,
    after: &str,
    label: &str,
) -> Result<(), String> {
    check_managed_text_state(path, before, after, label)?;
    if read_optional_text(path, label)?.as_deref() == Some(after) {
        return Ok(());
    }
    atomic_write_replace(path, after)
}

fn parse_init_issues(text: &str) -> Result<Vec<Issue>, String> {
    let mut issues = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let issue = serde_json::from_str::<Issue>(line).map_err(|error| {
            format!(
                "cannot initialize malformed board line {}: {}",
                index + 1,
                error
            )
        })?;
        issues.push(issue);
    }
    Ok(issues)
}

fn init_managed_changed(managed: &InitManagedText) -> bool {
    managed.before.as_deref() != Some(managed.after.as_str())
}

fn init_transaction_changed(transaction: &BoardInitTransaction) -> bool {
    init_managed_changed(&transaction.issues)
        || init_managed_changed(&transaction.sessions)
        || init_managed_changed(&transaction.board)
        || transaction
            .gitignore
            .as_ref()
            .is_some_and(init_managed_changed)
        || transaction
            .workflow
            .as_ref()
            .is_some_and(init_managed_changed)
        || transaction.order.as_ref().is_some_and(init_managed_changed)
        || transaction
            .readme
            .as_ref()
            .is_some_and(init_managed_changed)
}

fn build_board_init(base: &Path) -> Result<BoardInitPreparation, String> {
    let issues_before = read_optional_text(&base.join(".manna/issues.jsonl"), "issues board")?;
    let issues_after = issues_before.clone().unwrap_or_default();
    let issues = parse_init_issues(&issues_after)?;
    let sessions_before =
        read_optional_text(&base.join(".manna/sessions.jsonl"), "session journal")?;
    let sessions_after = sessions_before.clone().unwrap_or_default();
    let board_before = read_optional_text(&base.join(BOARD_FILE), "board identity")?;
    let existing_board = board_before
        .as_deref()
        .map(serde_yaml::from_str::<BoardConfig>)
        .transpose()
        .map_err(|error| format!("invalid board identity: {}", error))?;
    if existing_board
        .as_ref()
        .is_some_and(|board| board.version != 1)
    {
        return Err("unsupported Manna board identity version".to_string());
    }

    let workflow_before = read_optional_text(&base.join(WORKFLOW_FILE), "workflow config")?;
    let existing_workflow = workflow_before
        .as_deref()
        .map(serde_yaml::from_str::<WorkflowConfig>)
        .transpose()
        .map_err(|error| format!("invalid workflow config: {}", error))?;
    if let Some(config) = existing_workflow.as_ref() {
        config.validate_loadable()?;
    }

    let strict_markers = workflow_markers_present(base, &issues);
    let board = match existing_board {
        Some(board) => board,
        None if strict_markers || issues.is_empty() => BoardConfig::strict(),
        None => BoardConfig::legacy(),
    };
    let board_after = match board_before.as_deref() {
        Some(existing) => existing.to_string(),
        None => serde_yaml::to_string(&board)
            .map_err(|error| format!("failed to serialize board identity: {}", error))?,
    };
    let board_managed = InitManagedText {
        before: board_before,
        after: board_after,
    };
    let issues_managed = InitManagedText {
        before: issues_before,
        after: issues_after,
    };
    let sessions_managed = InitManagedText {
        before: sessions_before,
        after: sessions_after,
    };

    if board.workflow == BoardMode::Legacy {
        if strict_markers || existing_workflow.is_some() {
            return Err(
                "legacy board identity conflicts with strict workflow markers; archive or migrate them explicitly"
                    .to_string(),
            );
        }
        let transaction = BoardInitTransaction {
            version: BOARD_INIT_VERSION,
            issues: issues_managed,
            sessions: sessions_managed,
            board: board_managed,
            gitignore: None,
            workflow: None,
            order: None,
            readme: None,
            integrity: String::new(),
        };
        return Ok(BoardInitPreparation {
            changed: init_transaction_changed(&transaction),
            transaction,
            strict: false,
            gitignore_updated: false,
            restored_config: false,
            old_workflow: false,
        });
    }

    if !strict_markers {
        validate_new_handoff_root(base)?;
    } else {
        reject_symlink(&base.join(HANDOFF_DIR), "handoff root")?;
    }

    let restored_config = workflow_before.is_none();
    let old_workflow = existing_workflow
        .as_ref()
        .is_some_and(|workflow| workflow.version < WORKFLOW_VERSION);
    let workflow_after = match workflow_before.as_deref() {
        Some(existing) => existing.to_string(),
        None => serde_yaml::to_string(&WorkflowConfig::default())
            .map_err(|error| format!("failed to serialize workflow config: {}", error))?,
    };
    let order_before = read_optional_text(&base.join(HANDOFF_ORDER_FILE), "handoff priority")?;
    let (order_after, readme_after) =
        render_presentation_files(base, &issues, order_before.as_deref())?;
    let readme_before = read_optional_text(&base.join(HANDOFF_README), "handoff README")?;

    let ignored = durable_visibility_paths()
        .map(|path| git_path_ignored(base, Path::new(path)))
        .collect::<Result<Vec<_>, _>>()?;
    let gitignore = if ignored.iter().any(|ignored| *ignored) {
        let before = read_optional_text(&base.join(".gitignore"), ".gitignore")?;
        let after = workflow_gitignore_content(before.as_deref().unwrap_or_default());
        Some(InitManagedText { before, after })
    } else {
        None
    };
    let gitignore_updated = gitignore.as_ref().is_some_and(init_managed_changed);

    let transaction = BoardInitTransaction {
        version: BOARD_INIT_VERSION,
        issues: issues_managed,
        sessions: sessions_managed,
        board: board_managed,
        gitignore,
        workflow: Some(InitManagedText {
            before: workflow_before,
            after: workflow_after,
        }),
        order: Some(InitManagedText {
            before: order_before,
            after: order_after,
        }),
        readme: Some(InitManagedText {
            before: readme_before,
            after: readme_after,
        }),
        integrity: String::new(),
    };
    Ok(BoardInitPreparation {
        changed: init_transaction_changed(&transaction),
        transaction,
        strict: true,
        gitignore_updated,
        restored_config,
        old_workflow,
    })
}

fn validate_board_init_transaction(
    base: &Path,
    path: &Path,
    transaction: &BoardInitTransaction,
    key: &[u8],
) -> Result<(), String> {
    if path != board_init_path(base) {
        return Err(format!(
            "board init journal has non-canonical path {}",
            path.display()
        ));
    }
    if transaction.version != BOARD_INIT_VERSION {
        return Err(format!(
            "unsupported board init journal version {}",
            transaction.version
        ));
    }
    let expected = board_init_signature(base, key, transaction)?;
    if !constant_time_eq(expected.as_bytes(), transaction.integrity.as_bytes()) {
        return Err("board init journal failed integrity verification".to_string());
    }
    if transaction.issues.after != transaction.issues.before.clone().unwrap_or_default() {
        return Err("board init cannot change existing issue bytes".to_string());
    }
    if transaction.sessions.after != transaction.sessions.before.clone().unwrap_or_default() {
        return Err("board init cannot change existing session bytes".to_string());
    }
    let issues = parse_init_issues(&transaction.issues.after)?;
    let board: BoardConfig = serde_yaml::from_str(&transaction.board.after)
        .map_err(|error| format!("invalid initialized board identity: {}", error))?;
    if board.version != 1 {
        return Err(format!(
            "unsupported initialized board identity version {}",
            board.version
        ));
    }
    if transaction.board.before.is_some()
        && transaction.board.before.as_deref() != Some(transaction.board.after.as_str())
    {
        return Err("board init cannot replace an existing board identity".to_string());
    }
    let inferred = if workflow_markers_present(base, &issues) || issues.is_empty() {
        BoardMode::Strict
    } else {
        BoardMode::Legacy
    };
    if transaction.board.before.is_none() && board.workflow != inferred {
        return Err("board init identity does not match the pre-init board shape".to_string());
    }

    match board.workflow {
        BoardMode::Legacy => {
            if transaction.gitignore.is_some()
                || transaction.workflow.is_some()
                || transaction.order.is_some()
                || transaction.readme.is_some()
                || workflow_markers_present(base, &issues)
            {
                return Err("legacy board init cannot publish strict workflow state".to_string());
            }
        }
        BoardMode::Strict => {
            let workflow = transaction
                .workflow
                .as_ref()
                .ok_or_else(|| "strict board init has no workflow config".to_string())?;
            if workflow.before.is_some()
                && workflow.before.as_deref() != Some(workflow.after.as_str())
            {
                return Err("board init cannot silently upgrade workflow config".to_string());
            }
            let config: WorkflowConfig = serde_yaml::from_str(&workflow.after)
                .map_err(|error| format!("invalid initialized workflow config: {}", error))?;
            config.validate_loadable()?;
            let order = transaction
                .order
                .as_ref()
                .ok_or_else(|| "strict board init has no handoff priority".to_string())?;
            let parsed_order = parse_order(&order.after)?;
            if serialize_order(&parsed_order)? != order.after {
                return Err("board init handoff priority is not canonical YAML".to_string());
            }
            let readme = transaction
                .readme
                .as_ref()
                .ok_or_else(|| "strict board init has no handoff README".to_string())?;
            let (_, expected_readme) =
                render_presentation_files(base, &issues, Some(&order.after))?;
            if readme.after != expected_readme {
                return Err("board init README is not the canonical generated index".to_string());
            }
            if let Some(gitignore) = transaction.gitignore.as_ref() {
                let expected =
                    workflow_gitignore_content(gitignore.before.as_deref().unwrap_or_default());
                if gitignore.after != expected {
                    return Err("board init Git visibility update is not canonical".to_string());
                }
            }
        }
    }
    Ok(())
}

fn check_init_managed(path: &Path, managed: &InitManagedText, label: &str) -> Result<(), String> {
    check_managed_text_state(path, managed.before.as_deref(), &managed.after, label)
}

fn install_init_managed(path: &Path, managed: &InitManagedText, label: &str) -> Result<(), String> {
    install_managed_text(path, managed.before.as_deref(), &managed.after, label)
}

fn pause_init_before_identity_for_test() {
    if std::env::var("MANNA_TESTING").as_deref() != Ok("1") {
        return;
    }
    let Ok(raw) = std::env::var("MANNA_TEST_INIT_PAUSE_BEFORE_IDENTITY_MS") else {
        return;
    };
    let Ok(milliseconds) = raw.parse::<u64>() else {
        return;
    };
    std::thread::sleep(std::time::Duration::from_millis(milliseconds.min(60_000)));
}

fn apply_board_init_files(base: &Path, transaction: &BoardInitTransaction) -> Result<(), String> {
    let issues = base.join(".manna/issues.jsonl");
    let sessions = base.join(".manna/sessions.jsonl");
    let board = base.join(BOARD_FILE);
    let gitignore = base.join(".gitignore");
    let workflow = base.join(WORKFLOW_FILE);
    let order = base.join(HANDOFF_ORDER_FILE);
    let readme = base.join(HANDOFF_README);

    check_init_managed(&issues, &transaction.issues, "issues board")?;
    check_init_managed(&sessions, &transaction.sessions, "session journal")?;
    check_init_managed(&board, &transaction.board, "board identity")?;
    if let Some(managed) = transaction.gitignore.as_ref() {
        check_init_managed(&gitignore, managed, ".gitignore")?;
    }
    if let Some(managed) = transaction.workflow.as_ref() {
        check_init_managed(&workflow, managed, "workflow config")?;
    }
    if let Some(managed) = transaction.order.as_ref() {
        check_init_managed(&order, managed, "handoff priority")?;
    }
    if let Some(managed) = transaction.readme.as_ref() {
        check_init_managed(&readme, managed, "handoff README")?;
    }

    safe_create_dir_all(base, Path::new(".manna"))?;
    install_init_managed(&issues, &transaction.issues, "issues board")?;
    install_init_managed(&sessions, &transaction.sessions, "session journal")?;
    if let Some(managed) = transaction.gitignore.as_ref() {
        install_init_managed(&gitignore, managed, ".gitignore")?;
    }
    if transaction.workflow.is_some() {
        safe_create_dir_all(base, Path::new(HANDOFF_DIR))?;
    }
    if let Some(managed) = transaction.workflow.as_ref() {
        install_init_managed(&workflow, managed, "workflow config")?;
    }
    if let Some(managed) = transaction.order.as_ref() {
        install_init_managed(&order, managed, "handoff priority")?;
    }
    if let Some(managed) = transaction.readme.as_ref() {
        install_init_managed(&readme, managed, "handoff README")?;
    }

    if transaction.workflow.is_some() {
        for relative in durable_visibility_paths() {
            if git_path_ignored(base, Path::new(relative))? {
                return Err(format!(
                    "board init durable state is still ignored by Git: {}",
                    relative
                ));
            }
        }
    }

    // `board.yaml` is the commit point. A killed process can leave prepared
    // bytes plus this authenticated journal, but it can never publish a board
    // identity whose durable prerequisites are incomplete. The next init
    // replays the exact before/after states and removes the journal.
    pause_init_before_identity_for_test();
    install_init_managed(&board, &transaction.board, "board identity")
}

fn execute_board_init(
    base: &Path,
    store: &MannaStore,
    transaction: &BoardInitTransaction,
) -> Result<(), MannaError> {
    store.recover_initialize_with(|| apply_board_init_files(base, transaction))
}

fn write_board_init_transaction(
    base: &Path,
    transaction: &BoardInitTransaction,
) -> Result<PathBuf, String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = board_init_path(base);
    let key = load_recovery_key(base, true)?;
    let mut signed = transaction.clone();
    signed.integrity = board_init_signature(base, &key, &signed)?;
    validate_board_init_transaction(base, &path, &signed, &key)?;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize board init journal: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false).map_err(|error| {
        format!(
            "{}; a board initialization is already pending; rerun `agent-do manna init`",
            error
        )
    })?;
    Ok(path)
}

fn complete_board_init_path(
    base: &Path,
    store: &MannaStore,
    path: &Path,
    key: &[u8],
) -> Result<(), String> {
    safe_relative_path(
        base,
        path.strip_prefix(base)
            .map_err(|_| format!("board init journal is outside project: {}", path.display()))?,
        false,
    )?;
    reject_symlink(path, "board init journal")?;
    let mut file = File::open(path)
        .map_err(|error| format!("failed to open {}: {}", path.display(), error))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", path.display(), error))?;
    if !metadata.is_file() {
        return Err(format!(
            "board init journal is not a regular file: {}",
            path.display()
        ));
    }
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let transaction: BoardInitTransaction = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid board init journal {}: {}", path.display(), error))?;
    validate_board_init_transaction(base, path, &transaction, key)?;
    execute_board_init(base, store, &transaction).map_err(|error| error.to_string())?;
    remove_transaction_if_unchanged(path, &metadata, &text)
}

fn recover_board_init(base: &Path, store: &MannaStore) -> Result<usize, String> {
    let path = board_init_path(base);
    if !path.exists() {
        return Ok(0);
    }
    let key = load_recovery_key(base, false)?;
    complete_board_init_path(base, store, &path, &key)?;
    Ok(1)
}

fn run_board_init_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: BoardInitTransaction,
) -> Result<(), String> {
    let path = write_board_init_transaction(base, &transaction)?;
    let key = load_recovery_key(base, false)?;
    complete_board_init_path(base, store, &path, &key).map_err(|error| {
        format!(
            "board initialization is pending recovery: {}. Rerun `agent-do manna init`.",
            error
        )
    })
}

fn sync_stage_path(issue_id: &str) -> PathBuf {
    Path::new(HANDOFF_SYNC_STAGE_DIR).join(format!("{}.md", issue_id))
}

fn document_identity(base: &Path, relative: &Path) -> Result<Option<String>, String> {
    let relative = safe_relative_path(base, relative, true)?;
    let path = base.join(relative);
    reject_symlink(&path, "handoff sync document")?;
    match fs::read_to_string(&path) {
        Ok(text) => handoff_manna_id(&text).map(Some).ok_or_else(|| {
            format!(
                "handoff sync found an unstructured file at {}",
                path.display()
            )
        }),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("failed to read {}: {}", path.display(), error)),
    }
}

fn locate_sync_document(base: &Path, rename: &HandoffRename) -> Result<PathBuf, String> {
    let candidates = [
        PathBuf::from(&rename.from),
        sync_stage_path(&rename.issue_id),
        PathBuf::from(&rename.to),
    ];
    let mut matches = Vec::new();
    let mut seen = HashSet::new();
    for relative in candidates {
        if !seen.insert(relative.clone()) {
            continue;
        }
        if document_identity(base, &relative)?.as_deref() == Some(rename.issue_id.as_str()) {
            matches.push(relative);
        }
    }
    match matches.as_slice() {
        [path] => Ok(path.clone()),
        [] => Err(format!(
            "handoff sync cannot locate the sealed document for {}",
            rename.issue_id
        )),
        _ => Err(format!(
            "handoff sync found duplicate documents for {} at {}",
            rename.issue_id,
            matches
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>()
                .join(", ")
        )),
    }
}

fn validate_sync_file_state(
    base: &Path,
    transaction: &HandoffSyncTransaction,
) -> Result<(), String> {
    let by_id = transaction
        .before
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut sources = HashSet::new();
    let mut destinations = HashSet::new();
    for rename in &transaction.renames {
        if !sources.insert(rename.from.clone()) {
            return Err(format!("duplicate handoff sync source {}", rename.from));
        }
        if !destinations.insert(rename.to.clone()) {
            return Err(format!("duplicate handoff sync destination {}", rename.to));
        }
        let issue = by_id.get(rename.issue_id.as_str()).ok_or_else(|| {
            format!(
                "handoff sync rename targets missing item {}",
                rename.issue_id
            )
        })?;
        let from = safe_relative_path(base, Path::new(&rename.from), true)?;
        let to = safe_relative_path(base, Path::new(&rename.to), true)?;
        let stage = safe_relative_path(base, &sync_stage_path(&rename.issue_id), true)?;
        for relative in [&from, &to, &stage] {
            if !relative.starts_with(HANDOFF_DIR)
                || relative.starts_with(HANDOFF_ARCHIVE_DIR)
                || relative == Path::new(HANDOFF_README)
                || relative.extension().and_then(|value| value.to_str()) != Some("md")
            {
                return Err(format!(
                    "handoff sync path is outside generated work orders: {}",
                    relative.display()
                ));
            }
        }
        let location = locate_sync_document(base, rename)?;
        let text = fs::read_to_string(base.join(&location))
            .map_err(|error| format!("failed to read {}: {}", location.display(), error))?;
        validate_document(issue, &text).map_err(|error| {
            format!(
                "handoff sync refuses unsealed document {}: {}",
                rename.issue_id, error
            )
        })?;
        if git_path_ignored(base, &from)? {
            return Err(format!(
                "handoff sync source is ignored by Git: {}",
                from.display()
            ));
        }
        if git_path_ignored(base, &to)? {
            return Err(format!(
                "handoff sync destination is ignored by Git: {}",
                to.display()
            ));
        }
    }
    Ok(())
}

fn rename_sync_documents(base: &Path, transaction: &HandoffSyncTransaction) -> Result<(), String> {
    validate_sync_file_state(base, transaction)?;
    safe_create_dir_all(base, Path::new(HANDOFF_SYNC_STAGE_DIR))?;

    // Move every source into a unique internal staging path before installing
    // any destination. This handles A/B swaps and longer cycles without one
    // rename replacing another work order.
    for rename in &transaction.renames {
        let location = locate_sync_document(base, rename)?;
        let source = PathBuf::from(&rename.from);
        if location != source {
            continue;
        }
        let stage = sync_stage_path(&rename.issue_id);
        if path_exists(&base.join(&stage)) {
            return Err(format!(
                "handoff sync staging path is occupied: {}",
                stage.display()
            ));
        }
        fs::rename(base.join(&source), base.join(&stage)).map_err(|error| {
            format!(
                "failed to stage {} as {}: {}",
                source.display(),
                stage.display(),
                error
            )
        })?;
        sync_parent(&base.join(&source))?;
        sync_parent(&base.join(&stage))?;
    }

    for rename in &transaction.renames {
        let location = locate_sync_document(base, rename)?;
        let destination = PathBuf::from(&rename.to);
        if location == destination {
            continue;
        }
        let stage = sync_stage_path(&rename.issue_id);
        if location != stage {
            return Err(format!(
                "handoff sync document {} is not staged for installation",
                rename.issue_id
            ));
        }
        if path_exists(&base.join(&destination)) {
            return Err(format!(
                "handoff sync refuses to replace occupied destination {}",
                destination.display()
            ));
        }
        fs::rename(base.join(&stage), base.join(&destination)).map_err(|error| {
            format!(
                "failed to install {} as {}: {}",
                stage.display(),
                destination.display(),
                error
            )
        })?;
        sync_parent(&base.join(&stage))?;
        sync_parent(&base.join(&destination))?;
    }

    if base.join(HANDOFF_SYNC_STAGE_DIR).is_dir() {
        let mut remaining = fs::read_dir(base.join(HANDOFF_SYNC_STAGE_DIR))
            .map_err(|error| format!("failed to inspect handoff sync staging: {}", error))?;
        if remaining.next().is_none() {
            fs::remove_dir(base.join(HANDOFF_SYNC_STAGE_DIR))
                .map_err(|error| format!("failed to remove handoff sync staging: {}", error))?;
            sync_parent(&base.join(HANDOFF_SYNC_STAGE_DIR))?;
        }
    }
    validate_sync_file_state(base, transaction)
}

fn apply_handoff_sync_files(
    base: &Path,
    transaction: &HandoffSyncTransaction,
) -> Result<(), String> {
    let order = base.join(HANDOFF_ORDER_FILE);
    let readme = base.join(HANDOFF_README);
    check_managed_text_state(
        &order,
        transaction.order_before.as_deref(),
        &transaction.order_after,
        "handoff priority",
    )?;
    check_managed_text_state(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    validate_sync_file_state(base, transaction)?;

    rename_sync_documents(base, transaction)?;
    install_managed_text(
        &order,
        transaction.order_before.as_deref(),
        &transaction.order_after,
        "handoff priority",
    )?;
    install_managed_text(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    Ok(())
}

fn restore_managed_text(
    path: &Path,
    before: Option<&str>,
    after: &str,
    label: &str,
) -> Result<(), String> {
    let before = before.ok_or_else(|| {
        format!(
            "cannot roll back {} because the authenticated before state is absent",
            label
        )
    })?;
    check_managed_text_state(path, Some(before), after, label)?;
    if read_optional_text(path, label)?.as_deref() == Some(before) {
        return Ok(());
    }
    atomic_write_replace(path, before)
}

fn rollback_handoff_sync_files(
    base: &Path,
    transaction: &HandoffSyncTransaction,
) -> Result<(), String> {
    let order = base.join(HANDOFF_ORDER_FILE);
    let readme = base.join(HANDOFF_README);
    check_managed_text_state(
        &order,
        transaction.order_before.as_deref(),
        &transaction.order_after,
        "handoff priority",
    )?;
    check_managed_text_state(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    let mut reverse = transaction.clone();
    reverse.renames = transaction
        .renames
        .iter()
        .map(|rename| HandoffRename {
            issue_id: rename.issue_id.clone(),
            from: rename.to.clone(),
            to: rename.from.clone(),
        })
        .collect();
    rename_sync_documents(base, &reverse)?;
    restore_managed_text(
        &order,
        transaction.order_before.as_deref(),
        &transaction.order_after,
        "handoff priority",
    )?;
    restore_managed_text(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )
}

fn check_migration_document_state(
    base: &Path,
    migration_document: &MigrationDocument,
) -> Result<(), String> {
    let relative = safe_relative_path(base, Path::new(&migration_document.handoff), true)?;
    let target = base.join(relative);
    reject_symlink(&target, "legacy migration handoff")?;
    match fs::read_to_string(&target) {
        Ok(existing) if existing == migration_document.document => Ok(()),
        Ok(existing)
            if migration_document.previous_document.as_deref() == Some(existing.as_str()) =>
        {
            Ok(())
        }
        Ok(_) => Err(format!(
            "legacy migration handoff changed after admission was prepared: {}",
            migration_document.handoff
        )),
        Err(error)
            if error.kind() == std::io::ErrorKind::NotFound
                && migration_document.previous_document.is_none() =>
        {
            Ok(())
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Err(format!(
            "legacy migration handoff disappeared after admission was prepared: {}",
            migration_document.handoff
        )),
        Err(error) => Err(format!("failed to read {}: {}", target.display(), error)),
    }
}

fn check_legacy_source_archive_state(
    base: &Path,
    source_archive: &MigrationSourceArchive,
) -> Result<(), String> {
    let source = safe_relative_path(base, Path::new(&source_archive.source), true)?;
    let archive = safe_relative_path(base, Path::new(&source_archive.archive), true)?;
    let source_document =
        read_optional_migration_document(&base.join(&source), source.to_string_lossy().as_ref())?;
    let archive_document =
        read_optional_migration_document(&base.join(&archive), archive.to_string_lossy().as_ref())?;
    match (source_document.as_deref(), archive_document.as_deref()) {
        (Some(source), None) if source == source_archive.document => Ok(()),
        (None, Some(archive)) if archive == source_archive.document => Ok(()),
        (Some(_), Some(_)) => Err(format!(
            "legacy source {} and archive {} both exist",
            source_archive.source, source_archive.archive
        )),
        (None, None) => Err(format!(
            "legacy source {} and archive {} are both missing",
            source_archive.source, source_archive.archive
        )),
        (Some(_), None) => Err(format!(
            "legacy source changed after migration was prepared: {}",
            source_archive.source
        )),
        (None, Some(_)) => Err(format!(
            "legacy source archive changed after migration was prepared: {}",
            source_archive.archive
        )),
    }
}

fn retire_legacy_source(
    base: &Path,
    source_archive: &MigrationSourceArchive,
) -> Result<(), String> {
    check_legacy_source_archive_state(base, source_archive)?;
    let source = safe_relative_path(base, Path::new(&source_archive.source), true)?;
    let archive = safe_relative_path(base, Path::new(&source_archive.archive), true)?;
    let source_path = base.join(&source);
    let archive_path = base.join(&archive);
    if !source_path.exists() {
        return Ok(());
    }
    let archive_parent = archive
        .parent()
        .ok_or_else(|| format!("legacy source archive has no parent: {}", archive.display()))?;
    safe_create_dir_all(base, archive_parent)?;
    fs::rename(&source_path, &archive_path).map_err(|error| {
        format!(
            "failed to retire legacy source {} as {}: {}",
            source.display(),
            archive.display(),
            error
        )
    })?;
    sync_parent(&source_path)?;
    sync_parent(&archive_path)
}

fn apply_legacy_migration_files(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<(), String> {
    let gitignore = base.join(".gitignore");
    let workflow = base.join(WORKFLOW_FILE);
    let order = base.join(HANDOFF_ORDER_FILE);
    let readme = base.join(HANDOFF_README);

    // Validate every compare-and-swap precondition before the first write so
    // a concurrent human edit cannot leave a partly applied file set.
    check_managed_text_state(
        &gitignore,
        transaction.gitignore_before.as_deref(),
        &transaction.gitignore_after,
        ".gitignore",
    )?;
    check_managed_text_state(
        &workflow,
        transaction.workflow_before.as_deref(),
        &transaction.workflow_after,
        "workflow config",
    )?;
    if let Some(order_after) = transaction.order_after.as_deref() {
        check_managed_text_state(
            &order,
            transaction.order_before.as_deref(),
            order_after,
            "handoff priority",
        )?;
    }
    check_managed_text_state(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    for migration_document in &transaction.documents {
        check_migration_document_state(base, migration_document)?;
    }
    for source_archive in &transaction.source_archives {
        check_legacy_source_archive_state(base, source_archive)?;
    }

    install_managed_text(
        &gitignore,
        transaction.gitignore_before.as_deref(),
        &transaction.gitignore_after,
        ".gitignore",
    )?;
    safe_create_dir_all(base, Path::new(HANDOFF_DIR))?;
    safe_create_dir_all(base, Path::new(".manna"))?;
    install_managed_text(
        &workflow,
        transaction.workflow_before.as_deref(),
        &transaction.workflow_after,
        "workflow config",
    )?;
    if let Some(order_after) = transaction.order_after.as_deref() {
        install_managed_text(
            &order,
            transaction.order_before.as_deref(),
            order_after,
            "handoff priority",
        )?;
    }
    install_managed_text(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    for migration_document in &transaction.documents {
        install_transaction_document(
            base,
            Path::new(&migration_document.handoff),
            &migration_document.document,
        )?;
    }
    for source_archive in &transaction.source_archives {
        retire_legacy_source(base, source_archive)?;
    }

    for relative in durable_visibility_paths()
        .map(PathBuf::from)
        .chain(
            transaction
                .documents
                .iter()
                .map(|document| PathBuf::from(&document.handoff)),
        )
        .chain(
            transaction
                .source_archives
                .iter()
                .map(|archive| PathBuf::from(&archive.archive)),
        )
    {
        if git_path_ignored(base, &relative)? {
            return Err(format!(
                "legacy migration durable state is ignored by Git: {}",
                relative.display()
            ));
        }
    }
    Ok(())
}

fn archive_handoff(base: &Path, handoff: &Path, archive: &Path) -> Result<(), String> {
    let handoff = safe_relative_path(base, handoff, true)?;
    let archive = safe_relative_path(base, archive, true)?;
    if !archive.starts_with(HANDOFF_ARCHIVE_DIR) {
        return Err("handoff archive path is outside the canonical archive".to_string());
    }
    safe_create_dir_all(base, Path::new(HANDOFF_ARCHIVE_DIR))?;
    let source = base.join(&handoff);
    let target = base.join(&archive);
    reject_symlink(&source, "handoff")?;
    reject_symlink(&target, "handoff archive")?;
    if target.is_file() && !source.exists() {
        return Ok(());
    }
    if !source.is_file() {
        return Err(format!(
            "cannot archive missing handoff {}",
            handoff.display()
        ));
    }
    if target.exists() {
        return Err(format!(
            "handoff archive already exists: {}",
            archive.display()
        ));
    }
    fs::rename(&source, &target).map_err(|error| {
        format!(
            "failed to archive {} as {}: {}",
            handoff.display(),
            archive.display(),
            error
        )
    })?;
    sync_parent(&source)?;
    sync_parent(&target)
}

fn execute_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: &PairTransaction,
) -> Result<(), MannaError> {
    let handoff = Path::new(&transaction.handoff);
    match transaction.action {
        PairAction::Create => {
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("create transaction has no after row".to_string())
            })?;
            let document = transaction.document.as_deref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "create transaction has no handoff document".to_string(),
                )
            })?;
            store.recover_issue_with(after, || {
                install_transaction_document(base, handoff, document)
            })?;
        }
        PairAction::Attach | PairAction::Rebind => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "pair update transaction has no before row".to_string(),
                )
            })?;
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("pair update transaction has no after row".to_string())
            })?;
            let document = transaction.document.as_deref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "pair update transaction has no handoff document".to_string(),
                )
            })?;
            store.recover_replace_issue_with(before, after, || {
                install_transaction_document(base, handoff, document)
            })?;
        }
        PairAction::Rename => {
            let sync = transaction.sync.as_ref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "rename transaction has no handoff sync payload".to_string(),
                )
            })?;
            store.recover_replace_board_with(
                &sync.before,
                &sync.after,
                || apply_handoff_sync_files(base, sync),
                || Ok(()),
            )?;
        }
        PairAction::Detach => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no before row".to_string())
            })?;
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no after row".to_string())
            })?;
            let archive = transaction.archive.as_deref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no archive path".to_string())
            })?;
            store.recover_replace_issue_with(before, after, || {
                archive_handoff(base, handoff, Path::new(archive))
            })?;
        }
        PairAction::Delete => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("delete transaction has no before row".to_string())
            })?;
            let archive = transaction.archive.as_deref().ok_or_else(|| {
                MannaError::MutationRejected("delete transaction has no archive path".to_string())
            })?;
            store.recover_delete_issue_with(before, || {
                archive_handoff(base, handoff, Path::new(archive))
            })?;
        }
    }
    Ok(())
}

fn execute_legacy_migration(
    base: &Path,
    store: &MannaStore,
    transaction: &LegacyBoardTransaction,
) -> Result<(), MannaError> {
    let board_path = base.join(BOARD_FILE);
    store.recover_replace_board_with(
        &transaction.before,
        &transaction.after,
        || apply_legacy_migration_files(base, transaction),
        || {
            // Board identity is the commit point. Until this succeeds, every
            // ordinary write remains legacy or fail-closed; no reader can see
            // a strict identity backed by only part of the migrated state.
            install_managed_text(
                &board_path,
                transaction.board_before.as_deref(),
                &transaction.board_after,
                "board identity",
            )
        },
    )
}

fn write_legacy_migration_transaction(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<PathBuf, String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = legacy_migration_path(base);
    let key = load_recovery_key(base, true)?;
    let mut signed = transaction.clone();
    signed.integrity = legacy_migration_signature(base, &key, &signed)?;
    validate_legacy_migration_transaction(base, &path, &signed, &key)?;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize legacy migration: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false).map_err(|error| {
        format!(
            "{}; a legacy-board migration is already pending; rerun `agent-do manna migrate`",
            error
        )
    })?;
    Ok(path)
}

fn complete_legacy_migration_path(
    base: &Path,
    store: &MannaStore,
    path: &Path,
    key: &[u8],
) -> Result<TransactionOutcome, String> {
    safe_relative_path(
        base,
        path.strip_prefix(base).map_err(|_| {
            format!(
                "legacy migration path is outside project: {}",
                path.display()
            )
        })?,
        false,
    )?;
    reject_symlink(path, "legacy migration transaction")?;
    let mut file = File::open(path)
        .map_err(|error| format!("failed to open {}: {}", path.display(), error))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", path.display(), error))?;
    if !metadata.is_file() {
        return Err(format!(
            "legacy migration transaction is not a regular file: {}",
            path.display()
        ));
    }
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let transaction: LegacyBoardTransaction = serde_yaml::from_str(&text).map_err(|error| {
        format!(
            "invalid legacy migration transaction {}: {}",
            path.display(),
            error
        )
    })?;
    validate_legacy_migration_transaction(base, path, &transaction, key)?;
    match execute_legacy_migration(base, store, &transaction) {
        Ok(()) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::Applied)
        }
        Err(MannaError::RecoveryConflict(reason)) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::DiscardedConflict(reason))
        }
        Err(error) => Err(error.to_string()),
    }
}

fn ensure_presentation_scaffold(base: &Path, store: &MannaStore) -> Result<(), String> {
    if base.join(HANDOFF_ORDER_FILE).is_file() {
        return Ok(());
    }
    let issues = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let (order, readme) = render_presentation_files(base, &issues, None)?;
    ensure_workflow_tracked(base)?;
    atomic_write_replace(&base.join(HANDOFF_ORDER_FILE), &order)?;
    atomic_write_replace(&base.join(HANDOFF_README), &readme)
}

pub fn recover_legacy_migration(base: &Path, store: &MannaStore) -> Result<usize, String> {
    let path = legacy_migration_path(base);
    if !path.exists() {
        return Ok(0);
    }
    let key = load_recovery_key(base, false)?;
    match complete_legacy_migration_path(base, store, &path, &key)? {
        TransactionOutcome::Applied => {
            // Transactions written by the immediately preceding release did
            // not yet carry ordered presentation. Their authenticated board
            // admission remains valid; deterministically add the new derived
            // scaffold before ordinary strict commands resume.
            ensure_presentation_scaffold(base, store)?;
            Ok(1)
        }
        TransactionOutcome::DiscardedConflict(reason) => Err(format!(
            "legacy-board migration lost a concurrent update and was discarded safely: {}",
            reason
        )),
    }
}

fn run_legacy_migration_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: LegacyBoardTransaction,
) -> Result<(), String> {
    let path = write_legacy_migration_transaction(base, &transaction)?;
    let key = load_recovery_key(base, false)?;
    match complete_legacy_migration_path(base, store, &path, &key) {
        Ok(TransactionOutcome::Applied) => Ok(()),
        Ok(TransactionOutcome::DiscardedConflict(reason)) => Err(format!(
            "legacy-board migration lost a concurrent board update and was discarded safely: {}. Reload and retry.",
            reason
        )),
        Err(error) => Err(format!(
            "legacy-board migration is pending recovery: {}. Rerun `agent-do manna migrate`.",
            error
        )),
    }
}

fn complete_transaction_path(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    path: &Path,
    key: &[u8],
) -> Result<TransactionOutcome, String> {
    safe_relative_path(
        base,
        path.strip_prefix(base)
            .map_err(|_| format!("transaction path is outside project: {}", path.display()))?,
        false,
    )?;
    reject_symlink(path, "transaction")?;
    let mut file = File::open(path)
        .map_err(|error| format!("failed to open {}: {}", path.display(), error))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", path.display(), error))?;
    if !metadata.is_file() {
        return Err(format!(
            "transaction is not a regular file: {}",
            path.display()
        ));
    }
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let transaction: PairTransaction = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid pair transaction {}: {}", path.display(), error))?;
    validate_transaction(base, config, path, &transaction, key)?;
    match execute_transaction(base, store, &transaction) {
        Ok(()) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::Applied)
        }
        Err(MannaError::RecoveryConflict(reason)) => {
            if transaction.action == PairAction::Rename {
                let sync = transaction.sync.as_ref().ok_or_else(|| {
                    "conflicting rename transaction has no sync payload".to_string()
                })?;
                store
                    .recover_rollback_board_files(&sync.before, &sync.after, || {
                        rollback_handoff_sync_files(base, sync)
                    })
                    .map_err(|error| {
                        format!(
                            "handoff sync lost a concurrent board update but rollback is still pending: {}",
                            error
                        )
                    })?;
            }
            // Single-row pair recovery checks its target before touching the
            // file half. Whole-board rename recovery additionally rolls any
            // staged/applied file state back under the board lock above.
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::DiscardedConflict(reason))
        }
        Err(error) => Err(error.to_string()),
    }
}

fn run_transaction(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    transaction: PairTransaction,
) -> Result<(), String> {
    let path = write_transaction(base, config, &transaction)?;
    let key = load_recovery_key(base, false)?;
    match complete_transaction_path(base, store, config, &path, &key) {
        Ok(TransactionOutcome::Applied) => Ok(()),
        Ok(TransactionOutcome::DiscardedConflict(reason)) => Err(format!(
            "Manna pair transaction for {} lost a concurrent update and was discarded safely: {}. Reload the item and retry.",
            transaction.issue_id, reason
        )),
        Err(error) => Err(format!(
            "Manna pair transaction for {} is pending recovery: {}. Run `agent-do manna init`.",
            transaction.issue_id, error
        )),
    }
}

pub fn recover_pair_transactions(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
) -> Result<usize, String> {
    let relative = safe_relative_path(base, Path::new(TRANSACTION_DIR), true)?;
    let directory = base.join(relative);
    if !directory.exists() {
        return Ok(0);
    }
    let mut paths = fs::read_dir(&directory)
        .map_err(|error| format!("failed to inspect {}: {}", directory.display(), error))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("mn-") && name.ends_with(".yaml"))
        })
        .collect::<Vec<_>>();
    paths.sort();
    if paths.is_empty() {
        return Ok(0);
    }
    // A journal is published only after its key. The directory itself may be
    // visible earlier because writers create it before generating the key, so
    // an empty directory carries no authentication prerequisite.
    let key = load_recovery_key(base, false)?;
    let mut recovered = 0;
    for path in paths {
        match complete_transaction_path(base, store, config, &path, &key) {
            Ok(_) => recovered += 1,
            // Recovery scans are cooperative. Another process may complete
            // and unlink an authenticated journal after this process lists
            // the directory but before it opens or rechecks that path. An
            // absent path has no remaining intent to execute; the initiating
            // writer still uses run_transaction, which does not suppress it.
            Err(_) if !path.exists() => {}
            Err(error) => return Err(error),
        }
    }
    Ok(recovered)
}

fn sync_handoff_presentation_with_order(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    requested_order: Option<HandoffOrder>,
) -> Result<HandoffSyncResult, String> {
    validate_scaffold(base, config)?;
    let before = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let order_before = read_order_text(base)?;
    let stored = order_before.as_deref().map(parse_order).transpose()?;
    let order = match requested_order {
        Some(order) => normalize_order(&before, Some(&order))?,
        None => normalize_order(&before, stored.as_ref())?,
    };
    let plan = build_presentation_plan(base, &before, Some(&order))?;

    for issue in paired_items(&before) {
        validate_handoff(base, config, issue).map_err(|error| {
            format!(
                "cannot synchronize an invalid handoff for {}: {}",
                issue.id, error
            )
        })?;
    }

    let order_after = serialize_order(&plan.order)?;
    let readme_before = read_optional_text(&base.join(HANDOFF_README), "handoff README")?;
    let changed = before != plan.after
        || order_before.as_deref() != Some(order_after.as_str())
        || readme_before.as_deref() != Some(plan.readme.as_str());
    let held_claimed = plan
        .entries
        .iter()
        .filter(|entry| entry.held_claimed)
        .map(|entry| entry.issue_id.clone())
        .collect::<Vec<_>>();
    let result = HandoffSyncResult {
        renamed: plan.renames.len(),
        held_claimed,
        ordered_items: plan.order.items.len(),
        changed,
    };
    if !changed {
        return Ok(result);
    }

    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Rename,
        issue_id: HANDOFF_SYNC_TRANSACTION_ID.to_string(),
        before: None,
        after: None,
        handoff: HANDOFF_DIR.to_string(),
        archive: None,
        document: None,
        sync: Some(HandoffSyncTransaction {
            before,
            after: plan.after,
            renames: plan.renames,
            order_before,
            order_after,
            readme_before,
            readme_after: plan.readme,
        }),
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(result)
}

pub fn sync_handoff_presentation(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
) -> Result<HandoffSyncResult, String> {
    sync_handoff_presentation_with_order(base, store, config, None)
}

pub fn set_handoff_priority(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue_id: &str,
    position: usize,
) -> Result<HandoffSyncResult, String> {
    let issues = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let order_text = read_order_text(base)?;
    let stored = order_text.as_deref().map(parse_order).transpose()?;
    let mut order = normalize_order(&issues, stored.as_ref())?;
    let Some(index) = order.items.iter().position(|id| id == issue_id) else {
        return Err(format!(
            "{} is not an item with an authoritative handoff",
            issue_id
        ));
    };
    if position == 0 || position > order.items.len() {
        return Err(format!(
            "priority must be between 1 and {}, got {}",
            order.items.len(),
            position
        ));
    }
    let id = order.items.remove(index);
    order.items.insert(position - 1, id);
    sync_handoff_presentation_with_order(base, store, config, Some(order))
}

pub fn handoff_presentation_drift(
    base: &Path,
    issues: &[Issue],
) -> Result<Vec<HandoffPresentationDrift>, String> {
    let order_text = read_order_text(base)?
        .ok_or_else(|| format!("missing durable workflow file {}", HANDOFF_ORDER_FILE))?;
    let stored = parse_order(&order_text)?;
    let plan = build_presentation_plan(base, issues, Some(&stored))?;
    let mut findings = Vec::new();
    if order_text != serialize_order(&plan.order)? {
        findings.push(HandoffPresentationDrift {
            issue_id: None,
            rule: "handoff_order",
            detail: format!(
                "{} is not normalized to the current active paired item set",
                HANDOFF_ORDER_FILE
            ),
        });
    }
    for entry in &plan.entries {
        if entry.actual_path.as_deref() != Some(entry.expected_path.as_str()) {
            let hold = if entry.held_claimed {
                "; rename is held until its live claim releases"
            } else {
                ""
            };
            findings.push(HandoffPresentationDrift {
                issue_id: Some(entry.issue_id.clone()),
                rule: "handoff_filename",
                detail: format!(
                    "handoff path is {}, expected {}{}",
                    entry.actual_path.as_deref().unwrap_or("missing"),
                    entry.expected_path,
                    hold
                ),
            });
        }
    }
    let planned_ids = plan
        .entries
        .iter()
        .map(|entry| entry.issue_id.as_str())
        .collect::<HashSet<_>>();
    for rename in plan
        .renames
        .iter()
        .filter(|rename| !planned_ids.contains(rename.issue_id.as_str()))
    {
        findings.push(HandoffPresentationDrift {
            issue_id: Some(rename.issue_id.clone()),
            rule: "handoff_filename",
            detail: format!(
                "completed handoff path is {}, expected unnumbered history path {}",
                rename.from, rename.to
            ),
        });
    }
    let readme = read_optional_text(&base.join(HANDOFF_README), "handoff README")?;
    if readme.as_deref() != Some(plan.readme.as_str()) {
        findings.push(HandoffPresentationDrift {
            issue_id: None,
            rule: "handoff_index",
            detail: format!("{} does not match current board priority", HANDOFF_README),
        });
    }
    Ok(findings)
}

fn prepare_bound_issue(issue: &Issue, document: String) -> Result<(Issue, String), String> {
    let binding = calculate_binding(&document)?;
    let mut bound = issue.clone();
    bound.handoff_digest = Some(binding);
    bound.updated_at = Utc::now();
    Ok((bound, document))
}

fn preflight_handoff(base: &Path, relative: &Path) -> Result<(), String> {
    safe_relative_path(base, relative, true)?;
    if git_path_ignored(base, relative)? {
        return Err(format!("handoff is ignored by Git: {}", relative.display()));
    }
    Ok(())
}

pub fn create_paired_issue(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
    requested: Option<&str>,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, requested)?;
    preflight_handoff(base, &relative)?;
    if path_exists(&base.join(&relative)) {
        return Err(format!(
            "refusing to overwrite existing handoff {}",
            relative.display()
        ));
    }
    let mut paired = issue.clone();
    paired.prompt = Some(relative.to_string_lossy().into_owned());
    let document = render_handoff(base, &paired)?;
    let (paired, document) = prepare_bound_issue(&paired, document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Create,
        issue_id: paired.id.clone(),
        before: None,
        after: Some(paired.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(paired)
}

pub fn attach_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
    requested: Option<&str>,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, after_metadata, requested)?;
    preflight_handoff(base, &relative)?;
    if path_exists(&base.join(&relative)) {
        return Err(format!("handoff already exists: {}", relative.display()));
    }
    let mut after = after_metadata.clone();
    after.prompt = Some(relative.to_string_lossy().into_owned());
    let document = render_handoff(base, &after)?;
    let (after, document) = prepare_bound_issue(&after, document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Attach,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

fn archive_path(issue: &Issue) -> PathBuf {
    Path::new(HANDOFF_ARCHIVE_DIR).join(format!(
        "{}-{}.md",
        issue.id,
        issue.updated_at.format("%Y%m%dT%H%M%S%.fZ")
    ))
}

pub fn detach_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    let archive = archive_path(before);
    let mut after = after_metadata.clone();
    after.prompt = None;
    after.handoff_digest = None;
    after.updated_at = Utc::now();
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Detach,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: Some(archive.to_string_lossy().into_owned()),
        document: None,
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

pub fn delete_paired_issue(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<(), String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    let archive = archive_path(issue);
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Delete,
        issue_id: issue.id.clone(),
        before: Some(issue.clone()),
        after: None,
        handoff: relative.to_string_lossy().into_owned(),
        archive: Some(archive.to_string_lossy().into_owned()),
        document: None,
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)
}

fn update_frontmatter_for_issue(text: &str, issue: &Issue) -> Result<String, String> {
    let (mut frontmatter, body) = split_handoff(text)?;
    frontmatter.workflow = WORKFLOW_VERSION;
    frontmatter.manna = issue.id.clone();
    frontmatter.track = issue.track.clone();
    frontmatter.source = issue.source.clone();
    frontmatter.inputs = issue.source.iter().cloned().collect();
    frontmatter.scope = issue.title.clone();
    render_document(&frontmatter, body)
}

fn commit_rebind(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
    document: String,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let (mut after, document) = prepare_bound_issue(after_metadata, document)?;
    after.prompt = before.prompt.clone();
    validate_document(&after, &document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Rebind,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

/// Explicitly approve the current handoff contents and bind them to the row.
/// This is the only operation allowed to consume an unsealed document.
pub fn seal_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let document = update_frontmatter_for_issue(&existing, issue)?;
    commit_rebind(base, store, config, issue, issue, document)
}

/// Give a track that has no pair an existing document at its canonical path:
/// the body is kept byte for byte, the frontmatter is normalized to the row,
/// and the binding is computed and stored in one attach transaction. A
/// document that does not validate refuses here and names the defect, so a
/// hand-written track order is never overwritten and never half-adopted.
pub fn adopt_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, None)?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let mut after = before.clone();
    after.prompt = Some(relative.to_string_lossy().into_owned());
    let document = update_frontmatter_for_issue(&existing, &after)?;
    let (after, document) = prepare_bound_issue(&after, document)?;
    validate_document(&after, &document).map_err(|error| {
        format!(
            "existing {} cannot be adopted as the track's work order: {}",
            relative.display(),
            error
        )
    })?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Attach,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

/// Rewrite a paired row's document from its metadata under the same pointer.
/// Used when an item becomes a track or a track becomes an item: the body's
/// protocol differs by kind, so the generated document is replaced in one
/// rebind transaction. The previous body is in Git history; the existing seal
/// is verified first so an unsealed edit cannot vanish in the conversion.
pub fn regenerate_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    validate_document(before, &existing).map_err(|error| {
        format!(
            "cannot convert {} while its handoff is unsealed: {}. Seal it explicitly first with `agent-do manna handoff seal {}`",
            before.id, error, before.id
        )
    })?;
    let mut after = after_metadata.clone();
    after.prompt = before.prompt.clone();
    let document = render_handoff(base, &after)?;
    commit_rebind(base, store, config, before, &after, document)
}

/// The handoff priority list as stored, or empty when the board has none.
/// Read-only; `sync` owns normalization.
pub fn handoff_order_ids(base: &Path) -> Vec<String> {
    read_order_text(base)
        .ok()
        .flatten()
        .and_then(|text| parse_order(&text).ok())
        .map(|order| order.items)
        .unwrap_or_default()
}

/// Propagate authoritative row metadata into a handoff only after proving the
/// existing body is still sealed. Ordinary updates cannot bless hand-edited
/// scope merely because some unrelated title or source field changed.
pub fn rebind_handoff_metadata(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    validate_document(before, &existing).map_err(|error| {
        format!(
            "cannot update Manna metadata while the handoff is unsealed: {}. Seal it explicitly first with `agent-do manna handoff seal {}`",
            error, before.id
        )
    })?;
    let document = update_frontmatter_for_issue(&existing, after_metadata)?;
    commit_rebind(base, store, config, before, after_metadata, document)
}

fn upgrade_legacy_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    let path = base.join(&relative);
    let old = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let body = if let Ok((_, body)) = split_handoff(&old) {
        body.to_string()
    } else {
        generated_body(issue)
    };
    let document = render_document(&frontmatter_for(base, issue), &body)?;
    let (after, document) = prepare_bound_issue(issue, document)?;
    validate_document(&after, &document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Rebind,
        issue_id: issue.id.clone(),
        before: Some(issue.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        sync: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

fn valid_claim_token_hash(value: Option<&str>) -> bool {
    value.is_some_and(|proof| {
        proof.strip_prefix("sha256:").is_some_and(|hex| {
            hex.len() == 64
                && hex
                    .bytes()
                    .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
        })
    })
}

fn release_invalid_legacy_claim(issue: &mut Issue) -> bool {
    let has_claim_state = issue.claimed_by.is_some()
        || issue.claimed_at.is_some()
        || issue.claim_token_hash.is_some()
        || issue.status == IssueStatus::InProgress;
    let coherent_live_claim = issue.status != IssueStatus::Done
        && issue.claimed_by.is_some()
        && issue.claimed_at.is_some()
        && valid_claim_token_hash(issue.claim_token_hash.as_deref());
    if !has_claim_state || coherent_live_claim {
        return false;
    }

    issue.claimed_by = None;
    issue.claimed_at = None;
    issue.claim_token_hash = None;
    if issue.status != IssueStatus::Done {
        issue.status = if issue.blocked_by.is_empty() {
            IssueStatus::Open
        } else {
            IssueStatus::Blocked
        };
    }
    true
}

fn legacy_migration_result(
    issues: &[Issue],
    migrated: bool,
    recovered: bool,
) -> LegacyMigrationResult {
    let paired_items = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Paired
            })
        })
        .count();
    let historical_rows = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::History
            })
        })
        .count();
    let exempt_rows = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Exempt
            })
        })
        .count();
    let released_claims = issues
        .iter()
        .filter(|issue| {
            issue
                .legacy_migration
                .as_ref()
                .is_some_and(|migration| migration.released_claimed_by.is_some())
        })
        .count();
    LegacyMigrationResult {
        migrated,
        recovered_transaction: recovered,
        paired_items,
        historical_rows,
        exempt_rows,
        released_claims,
    }
}

fn validate_migrated_board(base: &Path, issues: &[Issue]) -> Result<WorkflowConfig, String> {
    let config = load_workflow(base)?
        .ok_or_else(|| format!("migrated board is missing {}", WORKFLOW_FILE))?;
    config.validate()?;
    validate_scaffold(base, &config)?;
    for issue in issues {
        issue
            .validate()
            .map_err(|error| format!("invalid strict row {}: {}", issue.id, error))?;
    }
    for issue in issues.iter().filter(|issue| {
        issue.issue_type == IssueType::Item
            && (issue.status != IssueStatus::Done
                || issue.prompt.is_some()
                || issue.handoff_digest.is_some())
    }) {
        validate_handoff(base, &config, issue).map_err(|error| {
            format!(
                "migrated item {} has an invalid authoritative handoff: {}",
                issue.id, error
            )
        })?;
    }
    Ok(config)
}

fn migration_annotation_matches(issue: &Issue) -> bool {
    let Some(annotation) = issue.legacy_migration.as_ref() else {
        return false;
    };
    if annotation.version != LEGACY_MIGRATION_VERSION {
        return false;
    }
    match annotation.disposition {
        LegacyMigrationDisposition::Paired => {
            issue.issue_type == IssueType::Item
                && issue.status != IssueStatus::Done
                && issue.prompt.is_some()
                && issue.handoff_digest.is_some()
        }
        LegacyMigrationDisposition::History => {
            issue.status == IssueStatus::Done
                && issue.prompt.is_none()
                && issue.handoff_digest.is_none()
        }
        LegacyMigrationDisposition::Exempt => {
            issue.status != IssueStatus::Done
                && issue.issue_type != IssueType::Item
                && issue.prompt.is_none()
                && issue.handoff_digest.is_none()
        }
    }
}

fn path_contains_git_metadata(path: &Path) -> bool {
    path.components().any(|component| {
        matches!(
            component,
            Component::Normal(value) if value == std::ffi::OsStr::new(".git")
        )
    })
}

fn read_optional_migration_document(path: &Path, pointer: &str) -> Result<Option<String>, String> {
    reject_symlink(path, "legacy handoff pointer")?;
    let mut file = match File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(format!("failed to read {}: {}", pointer, error)),
    };
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", pointer, error))?;
    if !metadata.is_file() {
        return Err(format!(
            "legacy handoff pointer is not a regular file: {}",
            pointer
        ));
    }
    let mut document = String::new();
    file.read_to_string(&mut document)
        .map_err(|error| format!("failed to read {} as UTF-8 Markdown: {}", pointer, error))?;
    Ok(Some(document))
}

fn read_migration_source(base: &Path, pointer: &str) -> Result<MigrationSource, String> {
    let raw = Path::new(pointer);
    let root = base
        .canonicalize()
        .map_err(|error| format!("failed to resolve project root: {}", error))?;
    let resolved_absolute = if raw.is_absolute() {
        reject_symlink(raw, "legacy handoff pointer")?;
        Some(resolve_missing_leaf(raw.to_path_buf())?)
    } else {
        None
    };
    let local = if let Some(resolved) = resolved_absolute.as_deref() {
        resolved
            .strip_prefix(&root)
            .ok()
            .or_else(|| raw.strip_prefix(base).ok())
    } else {
        Some(raw)
    };
    if let Some(relative) = local {
        let relative = safe_relative_path(base, &normalize_relative(relative)?, true)?;
        if path_contains_git_metadata(&relative) {
            return Err(format!(
                "legacy handoff pointer cannot read Git metadata: {}",
                pointer
            ));
        }
        let path = base.join(&relative);
        let document = read_optional_migration_document(&path, pointer)?;
        return Ok(MigrationSource {
            provenance: relative.to_string_lossy().into_owned(),
            project_relative: Some(relative),
            document,
        });
    }

    if raw
        .extension()
        .and_then(|extension| extension.to_str())
        .is_none_or(|extension| !extension.eq_ignore_ascii_case("md"))
    {
        return Err(format!(
            "cross-project legacy handoff pointer must name a Markdown file: {}",
            pointer
        ));
    }
    if path_contains_git_metadata(raw)
        || resolved_absolute
            .as_deref()
            .is_some_and(path_contains_git_metadata)
    {
        return Err(format!(
            "legacy handoff pointer cannot read Git metadata: {}",
            pointer
        ));
    }
    Ok(MigrationSource {
        project_relative: None,
        provenance: pointer.to_string(),
        document: read_optional_migration_document(raw, pointer)?,
    })
}

fn legacy_source_archive_path(source: &Path) -> PathBuf {
    let digest = Sha256::digest(source.to_string_lossy().as_bytes());
    Path::new(LEGACY_SOURCE_ARCHIVE_DIR).join(format!("{:x}.source", digest))
}

fn local_legacy_source(issue: &Issue, base: &Path) -> Result<Option<PathBuf>, String> {
    let Some(annotation) = issue.legacy_migration.as_ref() else {
        return Ok(None);
    };
    if annotation.disposition != LegacyMigrationDisposition::Paired {
        return Ok(None);
    }
    let Some(pointer) = annotation.previous_prompt.as_deref() else {
        return Ok(None);
    };
    let raw = Path::new(pointer);
    if raw.is_absolute() {
        // External sources are evidence owned by another project. Migration
        // imports their bytes but never mutates that project.
        return Ok(None);
    }
    let relative = safe_relative_path(base, &normalize_relative(raw)?, true)?;
    if relative.starts_with(HANDOFF_DIR) {
        // A legacy file already inside `.handoff/` either becomes the
        // canonical target in place or remains canonical input for one of a
        // shared set. It is not a shadow root and must not be retired.
        return Ok(None);
    }
    if path_contains_git_metadata(&relative) {
        return Err(format!(
            "legacy handoff pointer cannot archive Git metadata: {}",
            pointer
        ));
    }
    Ok(Some(relative))
}

fn collect_legacy_source_archives(
    base: &Path,
    issues: &[Issue],
    documents: &[MigrationDocument],
) -> Result<Vec<MigrationSourceArchive>, String> {
    let documents_by_id = documents
        .iter()
        .map(|document| (document.issue_id.as_str(), document))
        .collect::<HashMap<_, _>>();
    let mut grouped: HashMap<PathBuf, (String, Vec<String>)> = HashMap::new();

    for issue in issues {
        let Some(source) = local_legacy_source(issue, base)? else {
            continue;
        };
        let migration_document = documents_by_id.get(issue.id.as_str()).ok_or_else(|| {
            format!(
                "legacy source {} has no canonical handoff document for {}",
                source.display(),
                issue.id
            )
        })?;
        let archive = legacy_source_archive_path(&source);
        let source_path = base.join(&source);
        let archive_path = base.join(&archive);
        let source_document =
            read_optional_migration_document(&source_path, source.to_string_lossy().as_ref())?;

        let Some(source_document) = source_document else {
            if let Some(archived) =
                read_optional_migration_document(&archive_path, archive.to_string_lossy().as_ref())?
            {
                if !migration_document.document.contains(&archived) {
                    return Err(format!(
                        "archived legacy source {} is not preserved by canonical handoff {}",
                        source.display(),
                        migration_document.handoff
                    ));
                }
            }
            continue;
        };
        if !migration_document.document.contains(&source_document) {
            return Err(format!(
                "legacy source {} changed after admission and is not preserved by canonical handoff {}",
                source.display(),
                migration_document.handoff
            ));
        }
        if archive_path.exists() {
            return Err(format!(
                "legacy source {} and its canonical archive {} both exist; resolve the duplicate before migration",
                source.display(),
                archive.display()
            ));
        }
        match grouped.entry(source) {
            std::collections::hash_map::Entry::Occupied(mut entry) => {
                if entry.get().0 != source_document {
                    return Err(
                        "legacy source changed while migration was being prepared".to_string()
                    );
                }
                entry.get_mut().1.push(issue.id.clone());
            }
            std::collections::hash_map::Entry::Vacant(entry) => {
                entry.insert((source_document, vec![issue.id.clone()]));
            }
        }
    }

    let mut archives = grouped
        .into_iter()
        .map(|(source, (document, mut issue_ids))| {
            issue_ids.sort();
            MigrationSourceArchive {
                archive: legacy_source_archive_path(&source)
                    .to_string_lossy()
                    .into_owned(),
                source: source.to_string_lossy().into_owned(),
                document,
                issue_ids,
            }
        })
        .collect::<Vec<_>>();
    archives.sort_by(|left, right| left.source.cmp(&right.source));
    Ok(archives)
}

fn strict_migration_document(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<MigrationDocument, String> {
    issue
        .validate()
        .map_err(|error| format!("invalid strict row {}: {}", issue.id, error))?;
    if issue.issue_type != IssueType::Item {
        return Err(format!(
            "strict handoff binding on {} does not belong to an item",
            issue.id
        ));
    }
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let path = base.join(&relative);
    reject_symlink(&path, "strict migration handoff")?;
    let document = fs::read_to_string(&path).map_err(|error| {
        format!(
            "failed to read strict handoff {}: {}",
            relative.display(),
            error
        )
    })?;
    validate_document(issue, &document).map_err(|error| {
        format!(
            "strict item {} has an invalid authoritative handoff: {}",
            issue.id, error
        )
    })?;
    Ok(MigrationDocument {
        issue_id: issue.id.clone(),
        handoff: relative.to_string_lossy().into_owned(),
        previous_document: Some(document.clone()),
        source_document: None,
        document,
    })
}

fn repair_annotated_legacy_pair(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<Option<(Issue, MigrationDocument)>, String> {
    let Some(annotation) = issue.legacy_migration.as_ref() else {
        return Ok(None);
    };
    if annotation.disposition != LegacyMigrationDisposition::Paired {
        return Ok(None);
    }
    let Some(previous_prompt) = annotation.previous_prompt.as_deref() else {
        return Ok(None);
    };
    let normalized = strip_prompt_annotation(previous_prompt);
    if normalized == previous_prompt || normalized.is_empty() {
        return Ok(None);
    }
    let source = read_migration_source(base, normalized)?;
    let Some(source_document) = source.document.as_deref() else {
        return Ok(None);
    };

    let previous = strict_migration_document(base, config, issue)?;
    let document = append_adopted_source(&previous.document, source_document, &source.provenance)?;
    let mut after = issue.clone();
    after
        .legacy_migration
        .as_mut()
        .expect("paired migration annotation exists")
        .previous_prompt = Some(source.provenance);
    after.handoff_digest = Some(calculate_binding(&document)?);
    after
        .validate()
        .map_err(|error| format!("cannot repair migrated row {}: {}", after.id, error))?;
    validate_document(&after, &document)?;
    Ok(Some((
        after,
        MigrationDocument {
            issue_id: issue.id.clone(),
            handoff: previous.handoff,
            previous_document: Some(previous.document),
            source_document: Some(source_document.to_string()),
            document,
        },
    )))
}

fn annotated_pointer_repair_matches(
    base: &Path,
    before: &Issue,
    after: &Issue,
) -> Result<bool, String> {
    if before.handoff_digest.is_none() || after.handoff_digest.is_none() {
        return Ok(false);
    }
    let Some(annotation) = before.legacy_migration.as_ref() else {
        return Ok(false);
    };
    if annotation.disposition != LegacyMigrationDisposition::Paired {
        return Ok(false);
    }
    let Some(previous_prompt) = annotation.previous_prompt.as_deref() else {
        return Ok(false);
    };
    let normalized = strip_prompt_annotation(previous_prompt);
    if normalized == previous_prompt || normalized.is_empty() {
        return Ok(false);
    }
    let source = read_migration_source(base, normalized)?;
    let mut expected = before.clone();
    expected
        .legacy_migration
        .as_mut()
        .expect("paired migration annotation exists")
        .previous_prompt = Some(source.provenance);
    expected.handoff_digest = after.handoff_digest.clone();
    Ok(&expected == after)
}

fn build_legacy_migration(
    base: &Path,
    before: Vec<Issue>,
) -> Result<LegacyBoardTransaction, String> {
    if before.is_empty() {
        return Err(
            "the Manna board is empty; run `agent-do manna init` instead of legacy migration"
                .to_string(),
        );
    }

    let migration_time = Utc::now();
    let config = WorkflowConfig::default();
    let mut after = Vec::with_capacity(before.len());
    let mut documents = Vec::new();
    let mut document_paths = HashSet::new();
    for original in &before {
        if original.handoff_digest.is_some() {
            let (issue, document) = match repair_annotated_legacy_pair(base, &config, original)? {
                Some(repair) => repair,
                None => (
                    original.clone(),
                    strict_migration_document(base, &config, original)?,
                ),
            };
            if !document_paths.insert(document.handoff.clone()) {
                return Err(format!(
                    "strict handoff path is shared by more than one row: {}",
                    document.handoff
                ));
            }
            documents.push(document);
            after.push(issue);
            continue;
        }
        if original.legacy_migration.is_some() {
            original.validate().map_err(|error| {
                format!("invalid previously migrated row {}: {}", original.id, error)
            })?;
            if !migration_annotation_matches(original) {
                return Err(format!(
                    "legacy migration annotation on {} is incomplete or inconsistent",
                    original.id
                ));
            }
            after.push(original.clone());
            continue;
        }

        let mut issue = original.clone();
        let raw_previous_prompt = prompt_pointer(original);
        let mut previous_prompt = raw_previous_prompt.clone();
        let released_owner = original.claimed_by.clone();
        let released = release_invalid_legacy_claim(&mut issue);
        if released {
            issue.updated_at = migration_time;
        }

        let disposition = if issue.status == IssueStatus::Done {
            issue.prompt = None;
            issue.handoff_digest = None;
            LegacyMigrationDisposition::History
        } else if issue.issue_type != IssueType::Item {
            issue.prompt = None;
            issue.handoff_digest = None;
            LegacyMigrationDisposition::Exempt
        } else {
            // A row binding is the strict authority marker. Frontmatter-like
            // source text without one remains legacy input and is wrapped,
            // never interpreted as an already-admitted work order.
            let source = raw_previous_prompt
                .as_deref()
                .map(|pointer| read_migration_source(base, pointer))
                .transpose()?;
            if let Some(source) = source.as_ref() {
                previous_prompt = Some(source.provenance.clone());
            }
            let requested = source
                .as_ref()
                .and_then(|source| source.project_relative.as_ref())
                .and_then(|pointer| {
                    canonical_handoff_path(
                        base,
                        &config,
                        &issue,
                        Some(pointer.to_string_lossy().as_ref()),
                    )
                    .ok()
                });
            let generated = canonical_handoff_path(base, &config, &issue, None)?;
            let relative = requested
                .filter(|path| !document_paths.contains(path.to_string_lossy().as_ref()))
                .unwrap_or(generated);
            if !document_paths.insert(relative.to_string_lossy().into_owned()) {
                return Err(format!(
                    "legacy handoff target is shared by more than one row: {}",
                    relative.display()
                ));
            }
            preflight_handoff(base, &relative)?;
            issue.prompt = Some(relative.to_string_lossy().into_owned());
            let previous_document = source
                .as_ref()
                .filter(|source| source.project_relative.as_ref() == Some(&relative))
                .and_then(|source| source.document.clone());
            let source_document = source.as_ref().and_then(|source| source.document.clone());
            let document =
                if let Some(source) = source.as_ref().filter(|source| source.document.is_some()) {
                    render_adopted_handoff(
                        base,
                        &issue,
                        source.document.as_deref().unwrap(),
                        &source.provenance,
                    )?
                } else {
                    render_handoff(base, &issue)?
                };
            issue.handoff_digest = Some(calculate_binding(&document)?);
            validate_document(&issue, &document)?;
            documents.push(MigrationDocument {
                issue_id: issue.id.clone(),
                handoff: relative.to_string_lossy().into_owned(),
                previous_document,
                source_document,
                document,
            });
            LegacyMigrationDisposition::Paired
        };
        issue.legacy_migration = Some(LegacyMigrationAnnotation {
            version: LEGACY_MIGRATION_VERSION,
            disposition,
            migrated_at: migration_time,
            previous_prompt,
            released_claimed_by: released.then_some(released_owner).flatten(),
        });
        issue
            .validate()
            .map_err(|error| format!("cannot migrate {}: {}", issue.id, error))?;
        after.push(issue);
    }

    let order_before = read_order_text(base)?;
    let stored_order = order_before.as_deref().map(parse_order).transpose()?;
    let order = migration_order(&before, &after, stored_order.as_ref())?;
    let order_after = serialize_order(&order)?;
    let readme_after = match build_presentation_plan(base, &after, Some(&order)) {
        Ok(presentation) => presentation.readme,
        Err(error) => render_unsynchronized_index(&order, &after, &error),
    };

    let source_archives = collect_legacy_source_archives(base, &after, &documents)?;
    let board_before = read_optional_text(&base.join(BOARD_FILE), "board identity")?;
    let board_after = match board_before.as_deref() {
        Some(existing)
            if serde_yaml::from_str::<BoardConfig>(existing).is_ok_and(|board| {
                board.workflow == BoardMode::Strict && board.migrated_from_legacy_at.is_some()
            }) =>
        {
            existing.to_string()
        }
        _ => {
            let mut board = BoardConfig::strict();
            board.migrated_from_legacy_at = Some(migration_time);
            serde_yaml::to_string(&board).map_err(|error| {
                format!("failed to serialize migrated board identity: {}", error)
            })?
        }
    };
    let workflow_after = serde_yaml::to_string(&config)
        .map_err(|error| format!("failed to serialize workflow config: {}", error))?;
    let gitignore_before = read_optional_text(&base.join(".gitignore"), ".gitignore")?;
    let gitignore_after =
        workflow_gitignore_content(gitignore_before.as_deref().unwrap_or_default());
    for document in &documents {
        check_migration_document_state(base, document)?;
    }
    Ok(LegacyBoardTransaction {
        version: LEGACY_MIGRATION_VERSION,
        before,
        after,
        documents,
        source_archives,
        gitignore_before,
        gitignore_after,
        board_before,
        board_after,
        workflow_before: read_optional_text(&base.join(WORKFLOW_FILE), "workflow config")?,
        workflow_after,
        order_before,
        order_after: Some(order_after),
        readme_before: read_optional_text(&base.join(HANDOFF_README), "handoff README")?,
        readme_after,
        integrity: String::new(),
    })
}

/// Admit a pre-workflow board into strict mode as one authenticated,
/// recoverable transaction. Ordinary strict writes never call this operation
/// or relax their pair validation.
pub fn migrate_legacy_board(
    base: &Path,
    store: &MannaStore,
) -> Result<LegacyMigrationResult, String> {
    store
        .validate_storage_root()
        .map_err(|error| error.to_string())?;
    let recovered = recover_legacy_migration(base, store)? > 0;
    let issues = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let board = load_board_config(base)?;
    let mut prepared_transaction = None;

    if let Some(identity) = board.as_ref() {
        if identity.workflow == BoardMode::Strict
            && identity.migrated_from_legacy_at.is_some()
            && validate_migrated_board(base, &issues).is_ok()
        {
            let transaction = build_legacy_migration(base, issues.clone())?;
            if transaction.before == transaction.after && transaction.source_archives.is_empty() {
                return Ok(legacy_migration_result(&issues, recovered, recovered));
            }
            prepared_transaction = Some(transaction);
        }
        if prepared_transaction.is_none() && identity.workflow == BoardMode::Strict {
            let active_items = issues.iter().filter(|issue| {
                issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done
            });
            let fully_strict = active_items
                .clone()
                .all(|issue| issue.prompt.is_some() && issue.handoff_digest.is_some());
            let has_strict_binding = issues.iter().any(|issue| issue.handoff_digest.is_some());
            if fully_strict
                && has_strict_binding
                && load_workflow(base)?.is_some()
                && validate_migrated_board(base, &issues).is_ok()
            {
                return Ok(legacy_migration_result(&issues, false, recovered));
            }
        }
    }

    let transaction = match prepared_transaction {
        Some(transaction) => transaction,
        None => build_legacy_migration(base, issues)?,
    };
    let migrated_rows = transaction.after.clone();
    run_legacy_migration_transaction(base, store, transaction)?;
    validate_migrated_board(base, &migrated_rows)?;
    Ok(legacy_migration_result(&migrated_rows, true, recovered))
}

pub fn initialize_workflow(
    base: &Path,
    store: &MannaStore,
) -> Result<Option<WorkflowInit>, String> {
    store
        .validate_storage_root()
        .map_err(|error| error.to_string())?;
    let recovered_init = recover_board_init(base, store)?;
    let recovered_migration = if store.is_initialized() {
        recover_legacy_migration(base, store)?
    } else {
        0
    };
    let preparation = build_board_init(base)?;
    if preparation.changed {
        run_board_init_transaction(base, store, preparation.transaction.clone())?;
    }
    if !store.is_initialized() {
        return Err("board initialization did not publish complete storage".to_string());
    }
    if !preparation.strict {
        return Ok(None);
    }

    let board = load_board_config(base)?
        .ok_or_else(|| format!("missing durable workflow file {}", BOARD_FILE))?;
    if board.workflow != BoardMode::Strict {
        return Err("board initialization published the wrong workflow mode".to_string());
    }
    let config = WorkflowConfig::default();
    let yaml = serde_yaml::to_string(&config)
        .map_err(|error| format!("failed to serialize workflow config: {}", error))?;
    validate_scaffold(base, &config)?;

    let recovered_transactions =
        recovered_init + recovered_migration + recover_pair_transactions(base, store, &config)?;
    let issues = store.load_issues().map_err(|error| error.to_string())?;

    let mut upgraded_items = 0;
    if preparation.old_workflow {
        for issue in issues.iter().filter(|issue| {
            issue.issue_type == IssueType::Item
                && issue.status != IssueStatus::Done
                && issue.prompt.is_some()
                && issue.handoff_digest.is_none()
        }) {
            upgrade_legacy_handoff(base, store, &config, issue)?;
            upgraded_items += 1;
        }
        atomic_write_replace(&workflow_path(base), &yaml)?;
    }

    let current = store.load_issues().map_err(|error| error.to_string())?;
    for issue in current
        .iter()
        .filter(|issue| issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done)
    {
        if issue.prompt.is_none() || issue.handoff_digest.is_none() {
            return Err(format!(
                "strict workflow item {} is missing its authoritative handoff pair",
                issue.id
            ));
        }
        validate_handoff(base, &config, issue).map_err(|error| {
            format!(
                "strict workflow item {} has an invalid handoff: {}",
                issue.id, error
            )
        })?;
    }
    Ok(Some(WorkflowInit {
        config,
        gitignore_updated: preparation.gitignore_updated,
        upgraded_items,
        restored_config: preparation.restored_config,
        recovered_transactions,
    }))
}

pub fn validate_scaffold(base: &Path, config: &WorkflowConfig) -> Result<(), String> {
    config.validate()?;
    let board = load_board_config(base)?
        .ok_or_else(|| format!("missing durable workflow file {}", BOARD_FILE))?;
    if board.workflow != BoardMode::Strict {
        return Err("board identity is not strict".to_string());
    }
    for relative in durable_paths() {
        safe_relative_path(base, Path::new(relative), false)?;
        let path = base.join(relative);
        if !path.is_file() {
            return Err(format!("missing durable workflow file {}", relative));
        }
        if git_path_ignored(base, Path::new(relative))? {
            return Err(format!(
                "durable workflow file {} is ignored by Git",
                relative
            ));
        }
    }
    Ok(())
}

pub fn validate_handoff(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<PathBuf, String> {
    validate_scaffold(base, config)?;
    let pointer = issue
        .prompt
        .as_deref()
        .ok_or_else(|| format!("{} has no canonical handoff pointer", issue.id))?;
    let relative = canonical_handoff_path(base, config, issue, Some(pointer))?;
    let path = base.join(&relative);
    reject_symlink(&path, "handoff")?;
    if !path.is_file() {
        return Err(format!("handoff does not exist: {}", relative.display()));
    }
    if git_path_ignored(base, &relative)? {
        return Err(format!("handoff is ignored by Git: {}", relative.display()));
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    validate_document(issue, &text)?;
    Ok(relative)
}

pub fn handoff_manna_id(text: &str) -> Option<String> {
    split_handoff(text)
        .ok()
        .map(|(frontmatter, _)| frontmatter.manna)
}

pub fn find_orphan_handoffs(base: &Path, issues: &[Issue]) -> Vec<(PathBuf, String)> {
    let root = base.join(HANDOFF_DIR);
    let by_id = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<std::collections::HashMap<_, _>>();
    let mut findings = Vec::new();
    let mut stack = vec![root];
    while let Some(directory) = stack.pop() {
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path == base.join(HANDOFF_README) || path.starts_with(base.join(HANDOFF_ARCHIVE_DIR))
            {
                continue;
            }
            let file_type = match entry.file_type() {
                Ok(file_type) => file_type,
                Err(_) => continue,
            };
            if file_type.is_symlink() {
                findings.push((path, "symlink inside canonical handoff root".to_string()));
            } else if file_type.is_dir() {
                stack.push(path);
            } else if path.extension().and_then(|extension| extension.to_str()) == Some("md") {
                let text = fs::read_to_string(&path).unwrap_or_default();
                let Some(manna_id) = handoff_manna_id(&text) else {
                    // `.handoff/` is also the durable home for research and
                    // session-continuation documents. Only structured Manna
                    // work orders participate in the orphan invariant.
                    continue;
                };
                match by_id.get(manna_id.as_str()).copied() {
                    None => findings.push((path, "handoff has no live Manna item".to_string())),
                    Some(issue) if !pairable(issue.issue_type) => findings.push((
                        path,
                        format!("handoff belongs to non-actionable {}", issue.issue_type),
                    )),
                    Some(issue)
                        if issue
                            .prompt
                            .as_deref()
                            .is_none_or(|pointer| base.join(pointer) != path) =>
                    {
                        findings.push((
                            path,
                            "handoff is not the item's canonical pointer".to_string(),
                        ))
                    }
                    Some(_) => {}
                }
            }
        }
    }
    findings
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use tempfile::TempDir;

    #[test]
    fn stage_zero_gitignore_upgrade_adds_missing_durable_rules_once() {
        let existing = "# agent-do workflow: .manna and .handoff are durable state\n!.manna/\n.manna/*\n!.manna/issues.jsonl\n!.manna/sessions.jsonl\n!.manna/board.yaml\n!.manna/workflow.yaml\n!.manna/drift.yaml\n.manna/board.lock\n.manna/transactions/\n!.handoff/\n!.handoff/**\n";
        let updated = workflow_gitignore_content(existing);

        assert_eq!(
            updated
                .lines()
                .filter(|line| *line == "!.manna/board.yaml")
                .count(),
            1
        );
        assert_eq!(
            updated
                .lines()
                .filter(|line| *line == ".manna/transactions/")
                .count(),
            1
        );
        assert_eq!(
            updated
                .lines()
                .filter(|line| *line == "!.manna/handoff-order.yaml")
                .count(),
            1
        );
        assert_eq!(
            updated
                .lines()
                .filter(|line| *line == "!.manna/federation.yaml")
                .count(),
            1
        );
        assert_eq!(workflow_gitignore_content(&updated), updated);
    }

    #[test]
    fn identityless_board_guidance_distinguishes_empty_from_legacy() {
        let temp = TempDir::new().unwrap();
        let empty_error = load_workflow_for_board(temp.path(), &[]).unwrap_err();
        assert!(empty_error.contains("agent-do manna init"));
        assert!(!empty_error.contains("agent-do manna migrate"));

        let legacy = vec![Issue::new("mn-a10001".to_string(), "Legacy row".to_string()).unwrap()];
        let legacy_error = load_workflow_for_board(temp.path(), &legacy).unwrap_err();
        assert!(legacy_error.contains("nonempty legacy board"));
        assert!(legacy_error.contains("agent-do manna migrate"));
        assert!(!legacy_error.contains("agent-do manna init"));
    }

    #[test]
    fn durable_board_files_are_findings_until_added_to_git() {
        let (temp, _, _) = setup();
        let untracked = untracked_durable_paths(temp.path()).unwrap();
        assert_eq!(
            untracked,
            durable_paths().map(PathBuf::from).to_vec(),
            "Git-visible files are not durable until the index owns them"
        );

        let added = Command::new("git")
            .current_dir(temp.path())
            .args(["add", "--"])
            .args(durable_paths())
            .status()
            .unwrap();
        assert!(added.success());
        assert!(untracked_durable_paths(temp.path()).unwrap().is_empty());
    }

    #[test]
    fn hmac_sha256_matches_rfc_4231_case_one() {
        let key = [0x0b_u8; 20];
        let digest = hmac_sha256(&key, b"Hi There");
        let actual = digest
            .iter()
            .map(|byte| format!("{:02x}", byte))
            .collect::<String>();
        assert_eq!(
            actual,
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
        );
    }

    fn setup() -> (TempDir, MannaStore, WorkflowConfig) {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let init = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        (temp, store, init.config)
    }

    #[test]
    fn interrupted_board_init_recovers_before_identity_and_is_byte_stable() {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        let preparation = build_board_init(temp.path()).unwrap();
        assert!(preparation.changed);
        assert!(preparation.strict);
        let path = write_board_init_transaction(temp.path(), &preparation.transaction).unwrap();

        // Reproduce a killed initializer after storage preparation but before
        // the identity commit point. The authenticated journal is the only
        // authority allowed to finish these exact bytes.
        safe_create_dir_all(temp.path(), Path::new(".manna")).unwrap();
        install_init_managed(
            &temp.path().join(".manna/issues.jsonl"),
            &preparation.transaction.issues,
            "issues board",
        )
        .unwrap();
        install_init_managed(
            &temp.path().join(".manna/sessions.jsonl"),
            &preparation.transaction.sessions,
            "session journal",
        )
        .unwrap();
        assert!(path.is_file());
        assert!(!temp.path().join(BOARD_FILE).exists());

        let recovered = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert_eq!(recovered.recovered_transactions, 1);
        validate_scaffold(temp.path(), &recovered.config).unwrap();
        assert!(!path.exists());
        assert_eq!(
            fs::read_dir(temp.path().join(TRANSACTION_DIR))
                .unwrap()
                .count(),
            0
        );

        let before = durable_paths()
            .into_iter()
            .map(|relative| fs::read(temp.path().join(relative)).unwrap())
            .collect::<Vec<_>>();
        let repeated = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert_eq!(repeated.recovered_transactions, 0);
        let after = durable_paths()
            .into_iter()
            .map(|relative| fs::read(temp.path().join(relative)).unwrap())
            .collect::<Vec<_>>();
        assert_eq!(after, before);
    }

    fn issue(id: &str, title: &str) -> Issue {
        Issue::new(id.to_string(), title.to_string()).unwrap()
    }

    fn legacy_board() -> (TempDir, MannaStore, Vec<Issue>) {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        fs::create_dir(temp.path().join(HANDOFF_DIR)).unwrap();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("legacy-research.md"),
            "Research context, not a strict work order.\n",
        )
        .unwrap();

        let track = {
            let mut row = issue("mn-a00001", "Legacy track");
            row.issue_type = IssueType::Track;
            row
        };
        let active = {
            let mut row = issue("mn-a00002", "Unpaired active item");
            row.track = Some(track.id.clone());
            row
        };
        let blocked = {
            let mut row = issue("mn-a00003", "Blocked unpaired item");
            row.track = Some(track.id.clone());
            row.blocked_by = vec![active.id.clone()];
            row.status = IssueStatus::Blocked;
            row
        };
        let claimed = {
            let mut row = issue("mn-a00004", "Claim without proof");
            row.track = Some(track.id.clone());
            row.status = IssueStatus::InProgress;
            row.claimed_by = Some("legacy-session".to_string());
            row.claimed_at = Some(Utc::now());
            row
        };
        let done = {
            let mut row = issue("mn-a00005", "Historical item");
            row.track = Some(track.id.clone());
            row.status = IssueStatus::Done;
            row.prompt = Some(".dev/session-prompts/deleted.md".to_string());
            row.claimed_by = Some("legacy-history".to_string());
            row.claimed_at = Some(Utc::now());
            row
        };
        let dream = {
            let mut row = issue("mn-a00006", "Parked dream");
            row.issue_type = IssueType::Dream;
            row.track = Some(track.id.clone());
            row
        };
        let rows = vec![track, active, blocked, claimed, done, dream];
        for row in &rows {
            store.append_issue(row).unwrap();
        }
        (temp, store, rows)
    }

    #[test]
    fn preexisting_handoff_directory_does_not_misclassify_a_legacy_board() {
        let (temp, store, _) = legacy_board();
        let initialized = initialize_workflow(temp.path(), &store).unwrap();
        assert!(initialized.is_none());
        assert_eq!(
            load_board_config(temp.path()).unwrap().unwrap().workflow,
            BoardMode::Legacy
        );
    }

    #[test]
    fn legacy_migration_pairs_history_and_exemptions_in_one_idempotent_pass() {
        let (temp, store, _) = legacy_board();
        assert!(initialize_workflow(temp.path(), &store).unwrap().is_none());

        let migrated = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(migrated.migrated);
        assert!(!migrated.recovered_transaction);
        assert_eq!(migrated.paired_items, 3);
        assert_eq!(migrated.historical_rows, 1);
        assert_eq!(migrated.exempt_rows, 2);
        assert_eq!(migrated.released_claims, 2);

        let rows = store.load_issues().unwrap();
        let config = validate_migrated_board(temp.path(), &rows).unwrap();
        for row in rows
            .iter()
            .filter(|row| row.issue_type == IssueType::Item && row.status != IssueStatus::Done)
        {
            validate_handoff(temp.path(), &config, row).unwrap();
        }
        let released = rows.iter().find(|row| row.id == "mn-a00004").unwrap();
        assert_eq!(released.status, IssueStatus::Open);
        assert!(released.claimed_by.is_none());
        assert_eq!(
            released
                .legacy_migration
                .as_ref()
                .unwrap()
                .released_claimed_by
                .as_deref(),
            Some("legacy-session")
        );
        let history = rows.iter().find(|row| row.id == "mn-a00005").unwrap();
        assert!(history.prompt.is_none());
        assert_eq!(
            history
                .legacy_migration
                .as_ref()
                .unwrap()
                .previous_prompt
                .as_deref(),
            Some(".dev/session-prompts/deleted.md")
        );
        let dream = rows.iter().find(|row| row.id == "mn-a00006").unwrap();
        assert!(dream.prompt.is_none());
        assert_eq!(
            dream.legacy_migration.as_ref().unwrap().disposition,
            LegacyMigrationDisposition::Exempt
        );

        let rows_before_replay = rows.clone();
        let documents_before_replay = rows
            .iter()
            .filter_map(|row| row.prompt.as_deref())
            .map(|path| {
                (
                    path.to_string(),
                    fs::read_to_string(temp.path().join(path)).unwrap(),
                )
            })
            .collect::<Vec<_>>();
        let replay = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(!replay.migrated);
        assert!(!replay.recovered_transaction);
        assert_eq!(store.load_issues().unwrap(), rows_before_replay);
        for (path, contents) in documents_before_replay {
            assert_eq!(
                fs::read_to_string(temp.path().join(path)).unwrap(),
                contents
            );
        }
        initialize_workflow(temp.path(), &store).unwrap().unwrap();
    }

    #[test]
    fn mixed_migration_preserves_strict_rows_and_adopts_legacy_work_orders() {
        let (temp, store, config) = setup();
        let strict = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00010", "Strict native item"),
            None,
        )
        .unwrap();
        let owner = SessionIdentity::from_token(
            "mixed-owner",
            "mixed-owner-token-0123456789abcdef0123456789abcdef",
        )
        .unwrap();
        let strict = store
            .claim_issue_checked(&strict.id, &owner, |row, _| {
                validate_handoff(temp.path(), &config, row).map(|_| ())
            })
            .unwrap();
        let strict_path = temp.path().join(strict.prompt.as_deref().unwrap());
        let strict_document = fs::read_to_string(&strict_path).unwrap();

        let legacy_text = "# Legacy launch order\n\nKeep this exact work order.\n";
        let mut legacy = issue("mn-a00011", "Legacy numbered item");
        legacy.status = IssueStatus::InProgress;
        legacy.claimed_by = Some("legacy-pid-owner".to_string());
        legacy.claimed_at = Some(Utc::now());
        legacy.prompt = Some(".handoff/01-mn-a00011-legacy-numbered-item.md".to_string());
        fs::write(
            temp.path().join(legacy.prompt.as_deref().unwrap()),
            legacy_text,
        )
        .unwrap();
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();

        let migrated = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(migrated.migrated);
        assert_eq!(migrated.paired_items, 1);
        assert_eq!(migrated.released_claims, 1);
        let rows = store.load_issues_strict().unwrap();
        let strict_after = rows.iter().find(|row| row.id == strict.id).unwrap();
        assert_eq!(strict_after, &strict);
        assert_eq!(fs::read_to_string(&strict_path).unwrap(), strict_document);
        let legacy_after = rows.iter().find(|row| row.id == legacy.id).unwrap();
        assert_eq!(legacy_after.status, IssueStatus::Open);
        assert!(legacy_after.claimed_by.is_none());
        assert_eq!(legacy_after.prompt, legacy.prompt);
        let adopted =
            fs::read_to_string(temp.path().join(legacy_after.prompt.as_deref().unwrap())).unwrap();
        assert!(adopted.contains(legacy_text));
        validate_document(legacy_after, &adopted).unwrap();

        let order = parse_order(&fs::read_to_string(temp.path().join(HANDOFF_ORDER_FILE)).unwrap())
            .unwrap();
        assert_eq!(order.items, vec![legacy.id.clone(), strict.id.clone()]);

        let board_before_replay = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let strict_before_replay = fs::read(&strict_path).unwrap();
        let adopted_before_replay =
            fs::read(temp.path().join(legacy_after.prompt.as_deref().unwrap())).unwrap();
        let replay = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(!replay.migrated);
        assert_eq!(
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap(),
            board_before_replay
        );
        assert_eq!(fs::read(&strict_path).unwrap(), strict_before_replay);
        assert_eq!(
            fs::read(temp.path().join(legacy_after.prompt.as_deref().unwrap())).unwrap(),
            adopted_before_replay
        );
        assert!(!legacy_migration_path(temp.path()).exists());

        store.release_issue(&strict.id, &owner).unwrap();
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let synchronized = store.load_issues_strict().unwrap();
        validate_migrated_board(temp.path(), &synchronized).unwrap();
        assert!(handoff_presentation_drift(temp.path(), &synchronized)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn migration_adopts_partial_frontmatter_with_a_legacy_claim_section() {
        let (temp, store, _) = setup();
        let mut legacy = issue("mn-a00014", "Partial frontmatter work order");
        legacy.source = Some("estate sweep fixture".to_string());
        legacy.prompt = Some(".handoff/partial-frontmatter.md".to_string());
        let legacy_text = format!(
            "---\nmanna: {}\ntrack: null\nsource: estate sweep fixture\n---\n\n# Existing work order\n\n## Claim\n\n```bash\nagent-do manna claim {}\n```\n\nPreserve this body exactly.\n",
            legacy.id, legacy.id
        );
        fs::write(
            temp.path().join(legacy.prompt.as_deref().unwrap()),
            &legacy_text,
        )
        .unwrap();
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        let row = store.load_issues_strict().unwrap().remove(0);
        let document =
            fs::read_to_string(temp.path().join(row.prompt.as_deref().unwrap())).unwrap();
        assert!(document.contains(&legacy_text));
        assert_eq!(
            document
                .lines()
                .filter(|line| line.trim() == format!("agent-do manna claim {}", row.id))
                .count(),
            2
        );
        validate_document(&row, &document).unwrap();
    }

    #[test]
    fn migration_ingests_absolute_sources_and_normalizes_project_provenance() {
        let (temp, store, _) = setup();
        let external = TempDir::new().unwrap();
        let external_path = external.path().join("cross-project-work-order.md");
        let external_text = "# Cross-project work order\n\nPreserve the external source.\n";
        fs::write(&external_path, external_text).unwrap();

        let project_source = temp
            .path()
            .join(".dev/session-prompts/in-project-work-order.md");
        fs::create_dir_all(project_source.parent().unwrap()).unwrap();
        let project_text = "# In-project work order\n\nagent-do manna claim mn-a00016\n\nPreserve the local source.\n";
        fs::write(&project_source, project_text).unwrap();

        let mut outside = issue("mn-a00015", "Cross-project absolute pointer");
        outside.prompt = Some(external_path.to_string_lossy().into_owned());
        let mut inside = issue("mn-a00016", "In-project absolute pointer");
        inside.description = Some(format!(
            "PROMPT: {} — ratified design; read before starting\nAdditional context.",
            project_source.display()
        ));
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        for row in [&outside, &inside] {
            serde_json::to_writer(&mut board, row).unwrap();
            writeln!(board).unwrap();
        }
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        let rows = store.load_issues_strict().unwrap();
        let outside = rows.iter().find(|row| row.id == outside.id).unwrap();
        let inside = rows.iter().find(|row| row.id == inside.id).unwrap();
        for (row, original, provenance) in [
            (
                outside,
                external_text,
                external_path.to_string_lossy().into_owned(),
            ),
            (
                inside,
                project_text,
                ".dev/session-prompts/in-project-work-order.md".to_string(),
            ),
        ] {
            let prompt = row.prompt.as_deref().unwrap();
            assert!(prompt.starts_with(".handoff/"));
            let document = fs::read_to_string(temp.path().join(prompt)).unwrap();
            assert!(document.contains(original));
            assert!(document.contains(&format!(
                "> Legacy migration source: {}",
                serde_json::to_string(&provenance).unwrap()
            )));
            assert_eq!(
                row.legacy_migration
                    .as_ref()
                    .unwrap()
                    .previous_prompt
                    .as_deref(),
                Some(provenance.as_str())
            );
            validate_document(row, &document).unwrap();
        }
        assert!(external_path.is_file());
        assert!(!project_source.exists());
        let archived = temp.path().join(legacy_source_archive_path(Path::new(
            ".dev/session-prompts/in-project-work-order.md",
        )));
        assert_eq!(fs::read_to_string(archived).unwrap(), project_text);
    }

    #[test]
    fn migration_repairs_an_admitted_board_with_an_unretired_local_source() {
        let (temp, store, _) = setup();
        let source = Path::new(".dev/session-prompts/pre-fix-work-order.md");
        fs::create_dir_all(temp.path().join(source).parent().unwrap()).unwrap();
        let source_text =
            "# Pre-fix work order\n\nagent-do manna claim mn-a00018\n\nPreserve me.\n";
        fs::write(temp.path().join(source), source_text).unwrap();
        let mut legacy = issue("mn-a00018", "Pre-fix admitted item");
        legacy.prompt = Some(source.to_string_lossy().into_owned());
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        let archive = legacy_source_archive_path(source);
        fs::rename(temp.path().join(&archive), temp.path().join(source)).unwrap();
        let board_before = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let row = store.load_issues_strict().unwrap().remove(0);
        let handoff = temp.path().join(row.prompt.as_deref().unwrap());
        let handoff_before = fs::read(&handoff).unwrap();

        let repaired = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(repaired.migrated);
        assert!(!temp.path().join(source).exists());
        assert_eq!(
            fs::read_to_string(temp.path().join(&archive)).unwrap(),
            source_text
        );
        assert_eq!(
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap(),
            board_before
        );
        assert_eq!(fs::read(&handoff).unwrap(), handoff_before);
        assert!(!migrate_legacy_board(temp.path(), &store).unwrap().migrated);
    }

    #[test]
    fn migration_repairs_a_previously_admitted_annotated_pointer() {
        let (temp, store, _) = setup();
        let source = Path::new(".dev/session-prompts/annotated-work-order.md");
        fs::create_dir_all(temp.path().join(source).parent().unwrap()).unwrap();
        let source_text = "# Annotated work order\n\nPreserve the ratified design.\n";
        fs::write(temp.path().join(source), source_text).unwrap();
        let annotated = format!(
            "{} — ratified design; read before starting",
            source.display()
        );
        let mut legacy = issue("mn-a00022", "Previously annotated pointer");
        // A prompt field is intentionally literal. This manufactures the
        // exact malformed annotation written by the preceding migration
        // release before description annotations were normalized.
        legacy.prompt = Some(annotated.clone());
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        let admitted = store.load_issues_strict().unwrap().remove(0);
        assert_eq!(
            admitted
                .legacy_migration
                .as_ref()
                .unwrap()
                .previous_prompt
                .as_deref(),
            Some(annotated.as_str())
        );
        let handoff_path = temp.path().join(admitted.prompt.as_deref().unwrap());
        let handoff_before = fs::read_to_string(&handoff_path).unwrap();
        assert!(!handoff_before.contains(source_text));
        assert!(temp.path().join(source).is_file());

        let repaired = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(repaired.migrated);
        let repaired = store.load_issues_strict().unwrap().remove(0);
        assert_eq!(
            repaired
                .legacy_migration
                .as_ref()
                .unwrap()
                .previous_prompt
                .as_deref(),
            Some(source.to_string_lossy().as_ref())
        );
        let handoff_after = fs::read_to_string(&handoff_path).unwrap();
        assert!(handoff_after.contains(source_text));
        let (_, body_before) = split_handoff(&handoff_before).unwrap();
        let completion = required_section_positions(body_before).unwrap()[4];
        let (_, body_after) = split_handoff(&handoff_after).unwrap();
        assert!(body_after.starts_with(&body_before[..completion]));
        assert!(body_after.ends_with(&body_before[completion..]));
        validate_document(&repaired, &handoff_after).unwrap();
        assert!(!temp.path().join(source).exists());
        assert_eq!(
            fs::read_to_string(temp.path().join(legacy_source_archive_path(source))).unwrap(),
            source_text
        );
        assert!(!migrate_legacy_board(temp.path(), &store).unwrap().migrated);
    }

    #[test]
    fn shared_local_source_is_archived_once_for_every_adopted_item() {
        let (temp, store, _) = setup();
        let source = Path::new(".dev/session-prompts/shared-work-order.md");
        fs::create_dir_all(temp.path().join(source).parent().unwrap()).unwrap();
        let source_text = "# Shared local source\n\nPreserve this for both items.\n";
        fs::write(temp.path().join(source), source_text).unwrap();
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        for mut row in [
            issue("mn-a00019", "First local source user"),
            issue("mn-a00020", "Second local source user"),
        ] {
            row.prompt = Some(source.to_string_lossy().into_owned());
            serde_json::to_writer(&mut board, &row).unwrap();
            writeln!(board).unwrap();
        }
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(!temp.path().join(source).exists());
        let archives = fs::read_dir(temp.path().join(LEGACY_SOURCE_ARCHIVE_DIR))
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(archives.len(), 1);
        assert_eq!(fs::read_to_string(archives[0].path()).unwrap(), source_text);
        for row in store.load_issues_strict().unwrap() {
            let handoff = fs::read_to_string(temp.path().join(row.prompt.unwrap())).unwrap();
            assert!(handoff.contains(source_text));
        }
    }

    #[test]
    fn migration_recovery_accepts_an_already_retired_local_source() {
        let (temp, store, _) = setup();
        let source = Path::new(".dev/session-prompts/interrupted-work-order.md");
        fs::create_dir_all(temp.path().join(source).parent().unwrap()).unwrap();
        let source_text = "# Interrupted source\n\nPreserve across recovery.\n";
        fs::write(temp.path().join(source), source_text).unwrap();
        let mut legacy = issue("mn-a00021", "Interrupted source migration");
        legacy.prompt = Some(source.to_string_lossy().into_owned());
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();

        let transaction =
            build_legacy_migration(temp.path(), store.load_issues().unwrap()).unwrap();
        assert_eq!(transaction.source_archives.len(), 1);
        write_legacy_migration_transaction(temp.path(), &transaction).unwrap();
        let archive = Path::new(&transaction.source_archives[0].archive);
        safe_create_dir_all(temp.path(), archive.parent().unwrap()).unwrap();
        fs::rename(temp.path().join(source), temp.path().join(archive)).unwrap();

        assert_eq!(recover_legacy_migration(temp.path(), &store).unwrap(), 1);
        assert!(!legacy_migration_path(temp.path()).exists());
        assert_eq!(
            fs::read_to_string(temp.path().join(archive)).unwrap(),
            source_text
        );
        validate_migrated_board(temp.path(), &store.load_issues_strict().unwrap()).unwrap();
    }

    #[test]
    fn migration_refuses_non_markdown_cross_project_sources_without_writing() {
        let (temp, store, _) = setup();
        let external = TempDir::new().unwrap();
        let external_path = external.path().join("not-a-work-order.txt");
        fs::write(&external_path, "not an admissible handoff\n").unwrap();
        let mut legacy = issue("mn-a00017", "Non-Markdown external pointer");
        legacy.prompt = Some(external_path.to_string_lossy().into_owned());
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        serde_json::to_writer(&mut board, &legacy).unwrap();
        writeln!(board).unwrap();
        board.sync_all().unwrap();
        let board_before = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("cross-project legacy handoff pointer must name a Markdown file"));
        assert_eq!(
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap(),
            board_before
        );
        assert!(!legacy_migration_path(temp.path()).exists());
    }

    #[test]
    fn mixed_migration_splits_duplicate_legacy_targets_without_losing_content() {
        let (temp, store, _) = setup();
        let legacy_text = "# Shared legacy work order\n\nPreserve the shared source.\n";
        let shared = ".handoff/01-mn-a00012-shared-work-order.md";
        fs::write(temp.path().join(shared), legacy_text).unwrap();
        let mut first = issue("mn-a00012", "First shared item");
        first.prompt = Some(shared.to_string());
        let mut second = issue("mn-a00013", "Second shared item");
        second.prompt = Some(shared.to_string());
        let mut board = OpenOptions::new()
            .append(true)
            .open(temp.path().join(".manna/issues.jsonl"))
            .unwrap();
        for row in [&first, &second] {
            serde_json::to_writer(&mut board, row).unwrap();
            writeln!(board).unwrap();
        }
        board.sync_all().unwrap();

        migrate_legacy_board(temp.path(), &store).unwrap();
        let rows = store.load_issues_strict().unwrap();
        let first = rows.iter().find(|row| row.id == first.id).unwrap();
        let second = rows.iter().find(|row| row.id == second.id).unwrap();
        assert_ne!(first.prompt, second.prompt);
        for row in [first, second] {
            let text =
                fs::read_to_string(temp.path().join(row.prompt.as_deref().unwrap())).unwrap();
            assert!(text.contains(legacy_text));
            validate_document(row, &text).unwrap();
        }
        validate_migrated_board(temp.path(), &rows).unwrap();
    }

    #[test]
    fn stale_legacy_writer_cannot_bypass_the_migrated_strict_board() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let legacy_snapshot = store.load_issues().unwrap();
        assert!(load_workflow_for_board(temp.path(), &legacy_snapshot)
            .unwrap()
            .is_none());
        migrate_legacy_board(temp.path(), &store).unwrap();

        let unpaired = issue("mn-a00007", "Stale legacy create");
        let error = store.append_issue(&unpaired).unwrap_err().to_string();
        assert!(error.contains("missing its authoritative handoff pair"));

        let current = store
            .load_issues()
            .unwrap()
            .into_iter()
            .find(|row| row.id == "mn-a00002")
            .unwrap();
        let session = SessionIdentity::from_token(
            "migration-race",
            "migration-race-token-0123456789abcdef0123456789abcdef",
        )
        .unwrap();
        let error = store
            .mutate_issue_metadata(&current.id, &session, |row, _| {
                row.title = "Stale legacy metadata".to_string();
                Ok(())
            })
            .unwrap_err()
            .to_string();
        assert!(error.contains("handoff transaction"));
        let error = store
            .delete_issue_owned(&current.id, &session)
            .unwrap_err()
            .to_string();
        assert!(error.contains("archive through the handoff transaction"));

        let handoff = temp.path().join(current.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nTampered after a stale legacy read.\n");
        fs::write(&handoff, text).unwrap();
        let error = store
            .claim_issue_checked(&current.id, &session, |row, board| {
                let config = load_workflow_for_board(temp.path(), board)?
                    .ok_or_else(|| "expected strict board".to_string())?;
                validate_handoff(temp.path(), &config, row)?;
                Ok(())
            })
            .unwrap_err()
            .to_string();
        assert!(error.contains("binding is stale"));
    }

    #[test]
    fn pending_legacy_migration_recovers_before_pair_journals() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let before = store.load_issues().unwrap();
        let transaction = build_legacy_migration(temp.path(), before).unwrap();
        write_legacy_migration_transaction(temp.path(), &transaction).unwrap();

        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &WorkflowConfig::default()).unwrap(),
            0
        );
        assert_eq!(recover_legacy_migration(temp.path(), &store).unwrap(), 1);
        assert!(!legacy_migration_path(temp.path()).exists());
        let rows = store.load_issues().unwrap();
        validate_migrated_board(temp.path(), &rows).unwrap();
    }

    #[test]
    fn tampered_legacy_migration_journal_cannot_mutate_the_board() {
        let (temp, store, original) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let transaction = build_legacy_migration(temp.path(), original.clone()).unwrap();
        let path = write_legacy_migration_transaction(temp.path(), &transaction).unwrap();
        let text = fs::read_to_string(&path).unwrap();
        fs::write(&path, text.replace("hmac-sha256:", "hmac-sha256:00")).unwrap();

        let error = recover_legacy_migration(temp.path(), &store).unwrap_err();
        assert!(error.contains("failed HMAC authentication"));
        assert_eq!(store.load_issues().unwrap(), original);
        assert!(path.is_file());
        assert!(!temp.path().join(WORKFLOW_FILE).exists());
    }

    #[test]
    fn legacy_migration_refuses_to_rewrite_a_board_with_a_malformed_line() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let board_path = temp.path().join(".manna/issues.jsonl");
        let mut original = fs::read_to_string(&board_path).unwrap();
        original.push_str("{not valid json}\n");
        fs::write(&board_path, &original).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("cannot migrate malformed board line"));
        assert_eq!(fs::read_to_string(&board_path).unwrap(), original);
        assert!(!legacy_migration_path(temp.path()).exists());
    }

    #[test]
    fn migrate_never_reseals_a_tampered_strict_handoff() {
        let (temp, store, config) = setup();
        let paired = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "Already strict"),
            None,
        )
        .unwrap();
        let digest = paired.handoff_digest.clone();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nUnsealed strict edit.\n");
        fs::write(&path, text).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid authoritative handoff"));
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
    }

    #[test]
    fn migrate_never_adopts_a_strict_row_after_its_binding_is_deleted() {
        let (temp, store, config) = setup();
        let paired = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00018", "Strict binding deletion"),
            None,
        )
        .unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let text = fs::read_to_string(&path).unwrap();
        let without_binding = text
            .lines()
            .filter(|line| !line.starts_with("binding:"))
            .collect::<Vec<_>>()
            .join("\n");
        fs::write(&path, without_binding).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid authoritative handoff"));
        assert_eq!(store.load_issues().unwrap(), vec![paired]);
        assert!(!legacy_migration_path(temp.path()).exists());
    }

    #[test]
    fn strict_workflow_scaffolds_and_binds_one_item() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Fix the prompt graph");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        assert!(paired.handoff_digest.is_some());
        assert!(validate_handoff(temp.path(), &config, &paired).is_ok());
    }

    #[test]
    fn handoff_paths_cannot_escape_or_cross_symlinks() {
        let (temp, _store, config) = setup();
        let item = issue("mn-abc123", "Bounded work");
        assert!(canonical_handoff_path(temp.path(), &config, &item, Some("../work.md")).is_err());
        assert!(
            canonical_handoff_path(temp.path(), &config, &item, Some(".handoffs/work.md")).is_err()
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            fs::remove_dir_all(temp.path().join(HANDOFF_DIR)).unwrap();
            let outside = TempDir::new().unwrap();
            symlink(outside.path(), temp.path().join(HANDOFF_DIR)).unwrap();
            assert!(
                canonical_handoff_path(temp.path(), &config, &item, Some(".handoff/work.md"))
                    .is_err()
            );
        }
    }

    #[test]
    fn loose_comment_cannot_satisfy_binding() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "One claim only");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        fs::write(&path, "<!-- agent-do manna claim mn-abc123 -->\n").unwrap();
        assert!(validate_handoff(temp.path(), &config, &paired).is_err());
    }

    #[test]
    fn any_unsealed_content_change_breaks_the_binding() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nExtra scope that was not sealed.\n");
        fs::write(&path, text).unwrap();
        let error = validate_handoff(temp.path(), &config, &paired).unwrap_err();
        assert!(error.contains("binding is stale"));
    }

    #[test]
    fn metadata_update_cannot_silently_seal_a_body_edit() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nUnapproved scope expansion.\n");
        fs::write(&path, text).unwrap();

        let mut renamed = paired.clone();
        renamed.title = "Unrelated metadata update".to_string();
        renamed.updated_at = Utc::now();
        let error =
            rebind_handoff_metadata(temp.path(), &store, &config, &paired, &renamed).unwrap_err();
        assert!(error.contains("unsealed"));
        assert_eq!(store.load_issues().unwrap()[0], paired);

        let sealed = seal_handoff(temp.path(), &store, &config, &paired).unwrap();
        assert!(validate_handoff(temp.path(), &config, &sealed).is_ok());
    }

    #[test]
    fn restoring_config_does_not_bless_an_unsealed_handoff() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let digest = paired.handoff_digest.clone();
        let handoff = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nUnsealed after config deletion.\n");
        fs::write(&handoff, text).unwrap();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();

        let error = initialize_workflow(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid handoff"));
        assert!(temp.path().join(WORKFLOW_FILE).is_file());
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
    }

    #[test]
    fn workflow_version_downgrade_does_not_reopen_the_seal() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let digest = paired.handoff_digest.clone();
        let handoff = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nAttempted downgrade reseal.\n");
        fs::write(&handoff, text).unwrap();
        fs::write(
            temp.path().join(WORKFLOW_FILE),
            "version: 1\nhandoff_dir: .handoff\n",
        )
        .unwrap();

        let error = initialize_workflow(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid handoff"));
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
        assert_eq!(load_workflow(temp.path()).unwrap().unwrap().version, 2);
    }

    #[test]
    fn interrupted_v1_migration_finishes_only_unbound_items() {
        let (temp, store, config) = setup();
        let first = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-abc123", "Already migrated"),
            None,
        )
        .unwrap();
        let second = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-def456", "Still legacy"),
            None,
        )
        .unwrap();
        let first_document =
            fs::read_to_string(temp.path().join(first.prompt.as_deref().unwrap())).unwrap();
        let mut legacy_second = second.clone();
        legacy_second.handoff_digest = None;
        store
            .recover_replace_issue(&second, &legacy_second)
            .unwrap();
        fs::write(
            temp.path().join(WORKFLOW_FILE),
            "version: 1\nhandoff_dir: .handoff\n",
        )
        .unwrap();

        let initialized = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert_eq!(initialized.upgraded_items, 1);
        let rows = store.load_issues().unwrap();
        let current_first = rows.iter().find(|row| row.id == first.id).unwrap();
        let current_second = rows.iter().find(|row| row.id == second.id).unwrap();
        assert_eq!(current_first.handoff_digest, first.handoff_digest);
        assert_eq!(
            fs::read_to_string(temp.path().join(first.prompt.as_deref().unwrap())).unwrap(),
            first_document
        );
        assert!(current_second.handoff_digest.is_some());
        validate_handoff(temp.path(), &config, current_second).unwrap();
        assert_eq!(load_workflow(temp.path()).unwrap().unwrap().version, 2);
    }

    #[test]
    fn authenticated_journal_still_cannot_target_outside_handoff() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Forged destination");
        item.prompt = Some("victim.md".to_string());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let mut transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item),
            handoff: "victim.md".to_string(),
            archive: None,
            document: Some(document),
            sync: None,
            integrity: String::new(),
        };
        let key = load_recovery_key(temp.path(), true).unwrap();
        transaction.integrity = transaction_signature(temp.path(), &key, &transaction).unwrap();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let path = transaction_path(temp.path(), &transaction.issue_id);
        fs::write(&path, serde_yaml::to_string(&transaction).unwrap()).unwrap();

        let error = recover_pair_transactions(temp.path(), &store, &config).unwrap_err();
        assert!(error.contains("under .handoff") || error.contains("must live under"));
        assert!(!temp.path().join("victim.md").exists());
        assert!(store.load_issues().unwrap().is_empty());
        assert!(path.is_file());
    }

    #[test]
    fn journal_signature_is_bound_to_the_project_root() {
        let (temp, _store, _config) = setup();
        let other = TempDir::new().unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Delete,
            issue_id: "mn-abc123".to_string(),
            before: Some(issue("mn-abc123", "Bound project")),
            after: None,
            handoff: ".handoff/mn-abc123-bound-project.md".to_string(),
            archive: Some(".handoff/.archive/mn-abc123-bound-project.md".to_string()),
            document: None,
            sync: None,
            integrity: String::new(),
        };
        let key = [7_u8; 32];
        let original = transaction_signature(temp.path(), &key, &transaction).unwrap();
        let copied = transaction_signature(other.path(), &key, &transaction).unwrap();
        assert_ne!(original, copied);
    }

    #[test]
    fn planted_unsigned_journal_is_never_executed() {
        let (temp, store, config) = setup();
        load_recovery_key(temp.path(), true).unwrap();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let path = transaction_path(temp.path(), "mn-abc123");
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Delete,
            issue_id: "mn-abc123".to_string(),
            before: Some(issue("mn-abc123", "Planted")),
            after: None,
            handoff: ".handoff/mn-abc123-planted.md".to_string(),
            archive: Some(".handoff/.archive/mn-abc123-forged.md".to_string()),
            document: None,
            sync: None,
            integrity: "hmac-sha256:00".to_string(),
        };
        fs::write(&path, serde_yaml::to_string(&transaction).unwrap()).unwrap();
        let error = recover_pair_transactions(temp.path(), &store, &config).unwrap_err();
        assert!(error.contains("failed HMAC authentication"), "{error}");
        assert!(store.load_issues().unwrap().is_empty());
        assert!(path.is_file());
    }

    #[test]
    fn no_replace_install_has_exactly_one_concurrent_winner() {
        let temp = TempDir::new().unwrap();
        let target = Arc::new(temp.path().join("journal.yaml"));
        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for contender in 0..12 {
            let target = Arc::clone(&target);
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                let payload = format!("writer:{}", contender);
                barrier.wait();
                (
                    payload.clone(),
                    atomic_write(&target, payload.as_bytes(), false),
                )
            }));
        }
        let outcomes = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect::<Vec<_>>();
        let winners = outcomes
            .iter()
            .filter(|(_, result)| result.is_ok())
            .collect::<Vec<_>>();
        assert_eq!(winners.len(), 1);
        assert_eq!(fs::read_to_string(&*target).unwrap(), winners[0].0);
    }

    #[test]
    fn empty_transaction_directory_does_not_require_a_recovery_key() {
        let (temp, store, config) = setup();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let key = recovery_key_path(temp.path()).unwrap();
        if key.is_file() {
            fs::remove_file(&key).unwrap();
        }
        assert!(!key.exists());
        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            0
        );
        assert!(!key.exists());
    }

    #[test]
    fn obsolete_authenticated_intent_is_discarded_without_applying_it() {
        let (temp, store, config) = setup();
        let before = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-abc123", "Original"),
            None,
        )
        .unwrap();
        let handoff = Path::new(before.prompt.as_deref().unwrap());
        let original_document = fs::read_to_string(temp.path().join(handoff)).unwrap();

        let mut stale_metadata = before.clone();
        stale_metadata.title = "Stale writer".to_string();
        stale_metadata.updated_at = Utc::now();
        let stale_document =
            update_frontmatter_for_issue(&original_document, &stale_metadata).unwrap();
        let (stale_after, stale_document) =
            prepare_bound_issue(&stale_metadata, stale_document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Rebind,
            issue_id: before.id.clone(),
            before: Some(before.clone()),
            after: Some(stale_after),
            handoff: handoff.to_string_lossy().into_owned(),
            archive: None,
            document: Some(stale_document),
            sync: None,
            integrity: String::new(),
        };
        let path = write_transaction(temp.path(), &config, &transaction).unwrap();

        let mut winner = before.clone();
        winner.description = Some("A different writer won".to_string());
        winner.updated_at = Utc::now();
        store.recover_replace_issue(&before, &winner).unwrap();

        let key = load_recovery_key(temp.path(), false).unwrap();
        let outcome = complete_transaction_path(temp.path(), &store, &config, &path, &key).unwrap();
        assert!(matches!(outcome, TransactionOutcome::DiscardedConflict(_)));
        assert!(!path.exists());
        assert_eq!(store.load_issues().unwrap()[0], winner);
        assert_eq!(
            fs::read_to_string(temp.path().join(handoff)).unwrap(),
            original_document
        );
    }

    #[test]
    fn pending_create_transaction_recovers_both_sides() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Interrupted create");
        let relative = canonical_handoff_path(temp.path(), &config, &item, None).unwrap();
        item.prompt = Some(relative.to_string_lossy().into_owned());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item.clone()),
            handoff: relative.to_string_lossy().into_owned(),
            archive: None,
            document: Some(document),
            sync: None,
            integrity: String::new(),
        };
        write_transaction(temp.path(), &config, &transaction).unwrap();

        assert!(store.load_issues().unwrap().is_empty());
        assert!(!temp.path().join(&relative).exists());
        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            1
        );
        assert_eq!(store.load_issues().unwrap().len(), 1);
        assert!(validate_handoff(temp.path(), &config, &item).is_ok());
        assert!(!transaction_path(temp.path(), &item.id).exists());
    }

    #[test]
    fn concurrent_recovery_tolerates_a_peer_removing_the_same_journal() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Concurrent recovery");
        let relative = canonical_handoff_path(temp.path(), &config, &item, None).unwrap();
        item.prompt = Some(relative.to_string_lossy().into_owned());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item.clone()),
            handoff: relative.to_string_lossy().into_owned(),
            archive: None,
            document: Some(document),
            sync: None,
            integrity: String::new(),
        };
        write_transaction(temp.path(), &config, &transaction).unwrap();

        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for _ in 0..12 {
            let base = temp.path().to_path_buf();
            let store = store.clone();
            let config = config.clone();
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                barrier.wait();
                recover_pair_transactions(&base, &store, &config)
            }));
        }
        for handle in handles {
            handle.join().unwrap().unwrap();
        }
        assert_eq!(store.load_issues().unwrap(), vec![item.clone()]);
        assert!(validate_handoff(temp.path(), &config, &item).is_ok());
        assert!(!transaction_path(temp.path(), &item.id).exists());
    }

    #[test]
    fn deleting_a_pair_archives_its_handoff_without_an_orphan() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Delete pair");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let original = temp.path().join(paired.prompt.as_deref().unwrap());
        delete_paired_issue(temp.path(), &store, &config, &paired).unwrap();
        assert!(store.load_issues().unwrap().is_empty());
        assert!(!original.exists());
        assert!(temp.path().join(archive_path(&paired)).is_file());
        assert!(find_orphan_handoffs(temp.path(), &[]).is_empty());
    }

    #[test]
    fn freeform_handoff_research_is_not_an_orphan_work_order() {
        let (temp, _store, _config) = setup();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("62-research.md"),
            "Research protocol without Manna frontmatter.\n",
        )
        .unwrap();
        assert!(find_orphan_handoffs(temp.path(), &[]).is_empty());

        let orphan = issue("mn-a00001", "Structured orphan");
        let document = render_handoff(temp.path(), &orphan).unwrap();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("mn-a00001-orphan.md"),
            document,
        )
        .unwrap();
        let findings = find_orphan_handoffs(temp.path(), &[]);
        assert_eq!(findings.len(), 1);
        assert!(findings[0].1.contains("no live Manna item"));
    }

    #[test]
    fn strict_scaffold_checks_the_board_file_visibility() {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let config = initialize_workflow(temp.path(), &store)
            .unwrap()
            .unwrap()
            .config;
        let mut gitignore = fs::read_to_string(temp.path().join(".gitignore")).unwrap_or_default();
        gitignore.push_str("\n.manna/issues.jsonl\n");
        fs::write(temp.path().join(".gitignore"), gitignore).unwrap();
        assert!(validate_scaffold(temp.path(), &config)
            .unwrap_err()
            .contains("issues.jsonl is ignored"));
    }

    #[test]
    fn ancestor_repository_ignore_rules_are_enforced() {
        let parent = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(parent.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        fs::write(parent.path().join(".gitignore"), "/nested/\n").unwrap();
        let nested = parent.path().join("nested");
        fs::create_dir(&nested).unwrap();
        let store = MannaStore::new(&nested);
        store.init().unwrap();
        let error = initialize_workflow(&nested, &store).unwrap_err();
        assert!(error.contains("still ignored by Git"));
    }

    #[test]
    fn sync_derives_dense_priority_blocker_gates_and_index() {
        let (temp, store, config) = setup();
        let first = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "First task"),
            None,
        )
        .unwrap();
        let second = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-b00002", "Second task"),
            None,
        )
        .unwrap();
        let third = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-c00003", "Third task"),
            None,
        )
        .unwrap();
        let owner =
            SessionIdentity::from_token("ses-order", "order-0123456789abcdef0123456789abcdef")
                .unwrap();
        store.add_blocker(&second.id, &first.id, &owner).unwrap();
        store.add_blocker(&third.id, &first.id, &owner).unwrap();
        store.add_blocker(&third.id, &second.id, &owner).unwrap();

        let result = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert!(result.changed);
        assert_eq!(result.renamed, 3);
        assert!(result.held_claimed.is_empty());
        let rows = store.load_issues().unwrap();
        assert_eq!(
            rows.iter()
                .find(|row| row.id == first.id)
                .unwrap()
                .prompt
                .as_deref(),
            Some(".handoff/01-mn-a00001-first-task.md")
        );
        assert_eq!(
            rows.iter()
                .find(|row| row.id == second.id)
                .unwrap()
                .prompt
                .as_deref(),
            Some(".handoff/02b01-mn-b00002-second-task.md")
        );
        assert_eq!(
            rows.iter()
                .find(|row| row.id == third.id)
                .unwrap()
                .prompt
                .as_deref(),
            Some(".handoff/03b02-mn-c00003-third-task.md")
        );
        for row in &rows {
            validate_handoff(temp.path(), &config, row).unwrap();
        }
        let index = fs::read_to_string(temp.path().join(HANDOFF_README)).unwrap();
        assert!(index.contains("| 03 | `mn-c00003` | blocked | `mn-a00001`, `mn-b00002` |"));
        assert!(handoff_presentation_drift(temp.path(), &rows)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn sync_expands_fixed_width_for_a_hundred_item_plan() {
        let (temp, store, config) = setup();
        let mut items = Vec::new();
        for number in 1..=100 {
            let id = format!("mn-l{number:05}");
            let title = format!("Large plan {number}");
            items.push(
                create_paired_issue(temp.path(), &store, &config, &issue(&id, &title), None)
                    .unwrap(),
            );
        }
        let owner = SessionIdentity::from_token(
            "ses-large-order",
            "large-order-0123456789abcdef0123456789abcdef",
        )
        .unwrap();
        store
            .add_blocker(&items[99].id, &items[0].id, &owner)
            .unwrap();

        let result = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert_eq!(result.ordered_items, 100);
        assert_eq!(result.renamed, 100);
        let rows = store.load_issues_strict().unwrap();
        assert_eq!(
            rows[0].prompt.as_deref(),
            Some(".handoff/001-mn-l00001-large-plan-1.md")
        );
        assert_eq!(
            rows[98].prompt.as_deref(),
            Some(".handoff/099-mn-l00099-large-plan-99.md")
        );
        assert_eq!(
            rows[99].prompt.as_deref(),
            Some(".handoff/100b001-mn-l00100-large-plan-100.md")
        );
        assert_eq!(
            ordered_name_parts(&items[99].id, rows[99].prompt.as_deref().unwrap()),
            Some((100, Some(1)))
        );
        let index = fs::read_to_string(temp.path().join(HANDOFF_README)).unwrap();
        assert!(index.contains("| 001 | `mn-l00001` | open | none |"));
        assert!(index.contains("| 100 | `mn-l00100` | blocked | `mn-l00001` |"));
        assert!(handoff_presentation_drift(temp.path(), &rows)
            .unwrap()
            .is_empty());

        let replay = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert!(!replay.changed);
        assert_eq!(replay.renamed, 0);
    }

    #[test]
    fn completed_pair_leaves_the_numbered_launch_plan() {
        let (temp, store, config) = setup();
        let item = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "Finished task"),
            None,
        )
        .unwrap();
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let numbered = ".handoff/01-mn-a00001-finished-task.md";
        assert!(temp.path().join(numbered).is_file());

        let owner =
            SessionIdentity::from_token("ses-done", "done-0123456789abcdef0123456789abcdef")
                .unwrap();
        store.claim_issue(&item.id, &owner).unwrap();
        store.complete_issue(&item.id, &owner).unwrap();

        let drift = handoff_presentation_drift(temp.path(), &store.load_issues().unwrap()).unwrap();
        assert!(drift.iter().any(|finding| {
            finding.issue_id.as_deref() == Some(item.id.as_str())
                && finding.detail.contains("unnumbered history path")
        }));
        let result = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert_eq!(result.renamed, 1);
        assert_eq!(result.ordered_items, 0);

        let completed = store.load_issues().unwrap().into_iter().next().unwrap();
        assert_eq!(
            completed.prompt.as_deref(),
            Some(".handoff/mn-a00001-finished-task.md")
        );
        assert!(!temp.path().join(numbered).exists());
        assert!(temp
            .path()
            .join(".handoff/mn-a00001-finished-task.md")
            .is_file());
        validate_handoff(temp.path(), &config, &completed).unwrap();
        assert!(
            parse_order(&fs::read_to_string(temp.path().join(HANDOFF_ORDER_FILE)).unwrap())
                .unwrap()
                .items
                .is_empty()
        );
        assert!(!fs::read_to_string(temp.path().join(HANDOFF_README))
            .unwrap()
            .contains(&item.id));
        assert!(
            handoff_presentation_drift(temp.path(), &store.load_issues().unwrap())
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn priority_move_handles_rename_cycles_and_is_idempotent() {
        let (temp, store, config) = setup();
        for (id, title) in [
            ("mn-a00001", "Alpha"),
            ("mn-b00002", "Beta"),
            ("mn-c00003", "Gamma"),
        ] {
            create_paired_issue(temp.path(), &store, &config, &issue(id, title), None).unwrap();
        }
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let moved = set_handoff_priority(temp.path(), &store, &config, "mn-c00003", 1).unwrap();
        assert_eq!(moved.renamed, 3);
        let rows = store.load_issues().unwrap();
        assert_eq!(
            rows.iter()
                .map(|row| row.prompt.as_deref().unwrap())
                .collect::<Vec<_>>(),
            vec![
                ".handoff/02-mn-a00001-alpha.md",
                ".handoff/03-mn-b00002-beta.md",
                ".handoff/01-mn-c00003-gamma.md",
            ]
        );
        for row in &rows {
            let text =
                fs::read_to_string(temp.path().join(row.prompt.as_deref().unwrap())).unwrap();
            assert_eq!(handoff_manna_id(&text).as_deref(), Some(row.id.as_str()));
        }
        let board = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let order = fs::read(temp.path().join(HANDOFF_ORDER_FILE)).unwrap();
        let index = fs::read(temp.path().join(HANDOFF_README)).unwrap();
        let replay = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert!(!replay.changed);
        assert_eq!(replay.renamed, 0);
        assert_eq!(
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap(),
            board
        );
        assert_eq!(
            fs::read(temp.path().join(HANDOFF_ORDER_FILE)).unwrap(),
            order
        );
        assert_eq!(fs::read(temp.path().join(HANDOFF_README)).unwrap(), index);
    }

    #[test]
    fn live_claim_reserves_number_and_holds_gate_rename_until_release() {
        let (temp, store, config) = setup();
        let first = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "Blocker"),
            None,
        )
        .unwrap();
        let second = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-b00002", "Claimed work"),
            None,
        )
        .unwrap();
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let owner =
            SessionIdentity::from_token("ses-claimed", "claimed-0123456789abcdef0123456789abcdef")
                .unwrap();
        store.claim_issue(&second.id, &owner).unwrap();
        store.add_blocker(&second.id, &first.id, &owner).unwrap();

        let held = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert_eq!(held.held_claimed, vec![second.id.clone()]);
        assert_eq!(held.renamed, 0);
        let claimed = store
            .load_issues()
            .unwrap()
            .into_iter()
            .find(|row| row.id == second.id)
            .unwrap();
        assert_eq!(
            claimed.prompt.as_deref(),
            Some(".handoff/02-mn-b00002-claimed-work.md")
        );
        let drift = handoff_presentation_drift(temp.path(), &store.load_issues().unwrap()).unwrap();
        assert!(drift.iter().any(|finding| {
            finding.issue_id.as_deref() == Some(second.id.as_str())
                && finding
                    .detail
                    .contains("held until its live claim releases")
        }));

        store.release_issue(&second.id, &owner).unwrap();
        let released = sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        assert_eq!(released.renamed, 1);
        assert!(released.held_claimed.is_empty());
        let row = store
            .load_issues()
            .unwrap()
            .into_iter()
            .find(|row| row.id == second.id)
            .unwrap();
        assert_eq!(
            row.prompt.as_deref(),
            Some(".handoff/02b01-mn-b00002-claimed-work.md")
        );
    }

    #[test]
    fn interrupted_multi_rename_recovers_board_order_and_index() {
        let (temp, store, config) = setup();
        for (id, title) in [
            ("mn-a00001", "Alpha"),
            ("mn-b00002", "Beta"),
            ("mn-c00003", "Gamma"),
        ] {
            create_paired_issue(temp.path(), &store, &config, &issue(id, title), None).unwrap();
        }
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let before = store.load_issues_strict().unwrap();
        let mut order =
            parse_order(&fs::read_to_string(temp.path().join(HANDOFF_ORDER_FILE)).unwrap())
                .unwrap();
        let id = order.items.remove(2);
        order.items.insert(0, id);
        let plan = build_presentation_plan(temp.path(), &before, Some(&order)).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Rename,
            issue_id: HANDOFF_SYNC_TRANSACTION_ID.to_string(),
            before: None,
            after: None,
            handoff: HANDOFF_DIR.to_string(),
            archive: None,
            document: None,
            sync: Some(HandoffSyncTransaction {
                before: before.clone(),
                after: plan.after.clone(),
                renames: plan.renames.clone(),
                order_before: read_order_text(temp.path()).unwrap(),
                order_after: serialize_order(&plan.order).unwrap(),
                readme_before: read_optional_text(
                    &temp.path().join(HANDOFF_README),
                    "handoff README",
                )
                .unwrap(),
                readme_after: plan.readme.clone(),
            }),
            integrity: String::new(),
        };
        let journal = write_transaction(temp.path(), &config, &transaction).unwrap();
        safe_create_dir_all(temp.path(), Path::new(HANDOFF_SYNC_STAGE_DIR)).unwrap();
        let first = &plan.renames[0];
        fs::rename(
            temp.path().join(&first.from),
            temp.path().join(sync_stage_path(&first.issue_id)),
        )
        .unwrap();

        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            1
        );
        assert!(!journal.exists());
        assert_eq!(store.load_issues().unwrap(), plan.after);
        assert_eq!(
            fs::read_to_string(temp.path().join(HANDOFF_ORDER_FILE)).unwrap(),
            serialize_order(&plan.order).unwrap()
        );
        assert_eq!(
            fs::read_to_string(temp.path().join(HANDOFF_README)).unwrap(),
            plan.readme
        );
        assert!(!temp.path().join(HANDOFF_SYNC_STAGE_DIR).exists());
    }

    #[test]
    fn concurrent_board_advance_rolls_back_a_partially_applied_sync() {
        let (temp, store, config) = setup();
        for (id, title) in [("mn-a00001", "Alpha"), ("mn-b00002", "Beta")] {
            create_paired_issue(temp.path(), &store, &config, &issue(id, title), None).unwrap();
        }
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
        let before = store.load_issues_strict().unwrap();
        let order_before = read_order_text(temp.path()).unwrap();
        let readme_before =
            read_optional_text(&temp.path().join(HANDOFF_README), "handoff README").unwrap();
        let mut order = parse_order(order_before.as_deref().unwrap()).unwrap();
        order.items.swap(0, 1);
        let plan = build_presentation_plan(temp.path(), &before, Some(&order)).unwrap();
        let sync = HandoffSyncTransaction {
            before: before.clone(),
            after: plan.after.clone(),
            renames: plan.renames.clone(),
            order_before: order_before.clone(),
            order_after: serialize_order(&plan.order).unwrap(),
            readme_before: readme_before.clone(),
            readme_after: plan.readme,
        };
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Rename,
            issue_id: HANDOFF_SYNC_TRANSACTION_ID.to_string(),
            before: None,
            after: None,
            handoff: HANDOFF_DIR.to_string(),
            archive: None,
            document: None,
            sync: Some(sync.clone()),
            integrity: String::new(),
        };
        write_transaction(temp.path(), &config, &transaction).unwrap();
        apply_handoff_sync_files(temp.path(), &sync).unwrap();

        let mut dream = issue("mn-d00004", "Concurrent intake");
        dream.issue_type = IssueType::Dream;
        store.append_issue(&dream).unwrap();
        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            1
        );

        let current = store.load_issues_strict().unwrap();
        assert_eq!(&current[..before.len()], before.as_slice());
        assert_eq!(current.last(), Some(&dream));
        assert_eq!(read_order_text(temp.path()).unwrap(), order_before);
        assert_eq!(
            read_optional_text(&temp.path().join(HANDOFF_README), "handoff README").unwrap(),
            readme_before
        );
        for row in &before {
            assert!(temp.path().join(row.prompt.as_deref().unwrap()).is_file());
        }
        assert!(!transaction_path(temp.path(), HANDOFF_SYNC_TRANSACTION_ID).exists());
    }

    #[test]
    fn init_adds_priority_scaffold_without_bricking_invalid_dependencies() {
        let (temp, store, config) = setup();
        let paired = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "Blocked by track"),
            None,
        )
        .unwrap();
        let mut track = issue("mn-b00002", "Umbrella");
        track.issue_type = IssueType::Track;
        store.append_issue(&track).unwrap();
        let owner =
            SessionIdentity::from_token("ses-init", "init-0123456789abcdef0123456789abcdef")
                .unwrap();
        store.add_blocker(&paired.id, &track.id, &owner).unwrap();
        fs::remove_file(temp.path().join(HANDOFF_ORDER_FILE)).unwrap();

        initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert!(temp.path().join(HANDOFF_ORDER_FILE).is_file());
        let readme = fs::read_to_string(temp.path().join(HANDOFF_README)).unwrap();
        assert!(readme.contains("Launch presentation is blocked"));
        assert!(load_workflow_for_board(temp.path(), &store.load_issues().unwrap()).is_ok());
        store.remove_blocker(&paired.id, &track.id, &owner).unwrap();
        sync_handoff_presentation(temp.path(), &store, &config).unwrap();
    }

    #[test]
    fn preceding_release_migration_journal_upgrades_presentation_after_recovery() {
        let (temp, store, _) = legacy_board();
        let before = store.load_issues_strict().unwrap();
        let mut transaction = build_legacy_migration(temp.path(), before).unwrap();
        transaction.order_before = None;
        transaction.order_after = None;
        transaction.readme_after =
            "# agent-do handoffs\n\nLegacy generated contract.\n".to_string();
        write_legacy_migration_transaction(temp.path(), &transaction).unwrap();

        assert_eq!(recover_legacy_migration(temp.path(), &store).unwrap(), 1);
        assert!(temp.path().join(HANDOFF_ORDER_FILE).is_file());
        assert!(fs::read_to_string(temp.path().join(HANDOFF_README))
            .unwrap()
            .contains("## Generated index"));
        validate_scaffold(temp.path(), &WorkflowConfig::default()).unwrap();
    }

    #[test]
    fn missing_workflow_config_is_corruption_not_legacy() {
        let (temp, store, _config) = setup();
        let item = issue("mn-abc123", "Strict marker");
        // Manufacture the impossible row through the recovery fixture path;
        // the public append path now correctly rejects unpaired strict items.
        store.recover_issue(&item).unwrap();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();
        let issues = store.load_issues().unwrap();
        assert!(load_workflow_for_board(temp.path(), &issues).is_err());
    }

    #[test]
    fn init_restores_a_deleted_strict_config_even_on_an_empty_board() {
        let (temp, store, _config) = setup();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();
        fs::remove_dir_all(temp.path().join(HANDOFF_DIR)).unwrap();
        assert!(load_workflow_for_board(temp.path(), &[]).is_err());
        let init = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert!(init.restored_config);
        assert!(temp.path().join(WORKFLOW_FILE).is_file());
        assert!(temp.path().join(HANDOFF_README).is_file());
    }
}
