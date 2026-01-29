//! Manna CLI - Issue tracking for AI agents.
//!
//! All output is YAML format for machine parsing.
//! Exit codes: 0=success, 1=user error, 2=system error.

use std::collections::HashSet;
use std::path::Path;

use chrono::Utc;
use clap::{Parser, Subcommand};
use serde::Serialize;

use manna_core::error::MannaError;
use manna_core::id::generate_unique_id;
use manna_core::issue::{Issue, IssueStatus};
use manna_core::store::MannaStore;

/// Exit codes
const EXIT_SUCCESS: i32 = 0;
const EXIT_USER_ERROR: i32 = 1;
const EXIT_SYSTEM_ERROR: i32 = 2;

#[derive(Parser)]
#[command(name = "manna-core")]
#[command(version)]
#[command(about = "Manna issue tracking system for AI agents", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Initialize .manna/ directory
    Init,

    /// Show current session status
    Status,

    /// Create a new issue
    Create {
        /// Issue title (1-500 characters)
        title: String,

        /// Optional description
        description: Option<String>,
    },

    /// Claim an issue for the current session
    Claim {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Mark an issue as done
    Done {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Abandon/release a claimed issue
    Abandon {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Add a blocker dependency
    Block {
        /// Issue ID to mark as blocked
        id: String,

        /// ID of the blocking issue
        blocker_id: String,
    },

    /// Remove a blocker dependency
    Unblock {
        /// Issue ID to unblock
        id: String,

        /// ID of the blocker to remove
        blocker_id: String,
    },

    /// List issues with optional status filter
    List {
        /// Filter by status (open, in_progress, blocked, done)
        #[arg(long)]
        status: Option<String>,
    },

    /// Show issue details
    Show {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Output context blob for AI agents
    Context {
        /// Maximum tokens for context (default 8000)
        #[arg(long, default_value = "8000")]
        max_tokens: usize,
    },
}

// ============================================================================
// YAML Response Types
// ============================================================================

#[derive(Serialize)]
struct SuccessResponse<T: Serialize> {
    success: bool,
    #[serde(flatten)]
    data: T,
}

#[derive(Serialize)]
struct ErrorResponse {
    success: bool,
    error: String,
}

#[derive(Serialize)]
struct IssueData {
    issue: Issue,
}

#[derive(Serialize)]
struct IssueListData {
    issues: Vec<IssueSummary>,
}

#[derive(Serialize)]
struct IssueSummary {
    id: String,
    title: String,
    status: IssueStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    claimed_by: Option<String>,
}

#[derive(Serialize)]
struct StatusData {
    session_id: String,
    claimed_issues: Vec<String>,
}

#[derive(Serialize)]
struct ContextData {
    context: String,
}

#[derive(Serialize)]
struct InitData {
    initialized: bool,
    path: String,
}

// ============================================================================
// Helper Functions
// ============================================================================

/// Get session ID from environment or generate default.
fn get_session_id() -> String {
    std::env::var("MANNA_SESSION_ID")
        .unwrap_or_else(|_| format!("ses_pid{}_{}", std::process::id(), Utc::now().timestamp()))
}

/// Output success response as YAML and exit with success code.
fn output_success<T: Serialize>(data: T) -> ! {
    let response = SuccessResponse {
        success: true,
        data,
    };
    println!(
        "{}",
        serde_yaml::to_string(&response).unwrap_or_else(|e| {
            format!("success: false\nerror: \"YAML serialization error: {}\"", e)
        })
    );
    std::process::exit(EXIT_SUCCESS);
}

/// Output error response as YAML and exit with specified code.
fn output_error(error: &str, exit_code: i32) -> ! {
    let response = ErrorResponse {
        success: false,
        error: error.to_string(),
    };
    println!(
        "{}",
        serde_yaml::to_string(&response).unwrap_or_else(|e| {
            format!("success: false\nerror: \"YAML serialization error: {}\"", e)
        })
    );
    std::process::exit(exit_code);
}

/// Convert MannaError to exit code.
fn error_to_exit_code(err: &MannaError) -> i32 {
    match err {
        MannaError::IssueNotFound(_) => EXIT_USER_ERROR,
        MannaError::IssueAlreadyExists(_) => EXIT_USER_ERROR,
        MannaError::InvalidStatusTransition { .. } => EXIT_USER_ERROR,
        MannaError::InvalidId(_) => EXIT_USER_ERROR,
        MannaError::Io(_) => EXIT_SYSTEM_ERROR,
        MannaError::Json(_) => EXIT_SYSTEM_ERROR,
        MannaError::NotInitialized => EXIT_USER_ERROR,
        MannaError::LockFailed(_) => EXIT_SYSTEM_ERROR,
    }
}

/// Handle MannaError by outputting YAML error and exiting.
fn handle_manna_error(err: MannaError) -> ! {
    let exit_code = error_to_exit_code(&err);
    output_error(&err.to_string(), exit_code);
}

/// Parse status string to IssueStatus.
fn parse_status(s: &str) -> Result<IssueStatus, String> {
    match s.to_lowercase().as_str() {
        "open" => Ok(IssueStatus::Open),
        "in_progress" => Ok(IssueStatus::InProgress),
        "blocked" => Ok(IssueStatus::Blocked),
        "done" => Ok(IssueStatus::Done),
        _ => Err(format!(
            "Invalid status '{}'. Valid options: open, in_progress, blocked, done",
            s
        )),
    }
}

/// Find issue by ID or exit with error.
fn find_issue(issues: &[Issue], id: &str) -> Issue {
    issues
        .iter()
        .find(|i| i.id == id)
        .cloned()
        .unwrap_or_else(|| {
            output_error(&format!("Issue {} not found", id), EXIT_USER_ERROR);
        })
}

// ============================================================================
// Command Implementations
// ============================================================================

fn cmd_init() -> ! {
    let store = MannaStore::new(Path::new("."));
    match store.init() {
        Ok(()) => output_success(InitData {
            initialized: true,
            path: ".manna".to_string(),
        }),
        Err(err) => handle_manna_error(err),
    }
}

fn cmd_status() -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let session_id = get_session_id();

    let claimed_issues: Vec<String> = match store.load_issues() {
        Ok(issues) => issues
            .iter()
            .filter(|i| i.claimed_by.as_ref() == Some(&session_id))
            .map(|i| i.id.clone())
            .collect(),
        Err(err) => handle_manna_error(err),
    };

    output_success(StatusData {
        session_id,
        claimed_issues,
    });
}

fn cmd_create(title: String, description: Option<String>) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Validate title
    if title.is_empty() || title.len() > 500 {
        output_error(
            &format!("Title must be 1-500 characters, got {}", title.len()),
            EXIT_USER_ERROR,
        );
    }

    // Get existing IDs for unique generation
    let existing_ids: HashSet<String> = match store.load_issues() {
        Ok(issues) => issues.into_iter().map(|i| i.id).collect(),
        Err(err) => handle_manna_error(err),
    };

    // Generate unique ID
    let id = generate_unique_id(&existing_ids);

    // Create issue
    let mut issue = match Issue::new(id, title) {
        Ok(i) => i,
        Err(e) => output_error(&e, EXIT_USER_ERROR),
    };

    // Set description if provided
    issue.description = description;

    // Append to store
    if let Err(err) = store.append_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_claim(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let session_id = get_session_id();

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Claim it
    if let Err(e) = issue.claim(session_id) {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_done(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Complete it
    if let Err(e) = issue.complete() {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_abandon(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Release it
    if let Err(e) = issue.release() {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_block(id: String, blocker_id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Verify blocker exists
    if !issues.iter().any(|i| i.id == blocker_id) {
        output_error(
            &format!("Blocker issue {} not found", blocker_id),
            EXIT_USER_ERROR,
        );
    }

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Add blocker
    issue.add_blocker(blocker_id);

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_unblock(id: String, blocker_id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Remove blocker
    issue.remove_blocker(&blocker_id);

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_list(status_filter: Option<String>) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Parse filter if provided
    let filter: Option<IssueStatus> = match status_filter {
        Some(s) => match parse_status(&s) {
            Ok(status) => Some(status),
            Err(e) => output_error(&e, EXIT_USER_ERROR),
        },
        None => None,
    };

    // Filter and map to summaries
    let summaries: Vec<IssueSummary> = issues
        .into_iter()
        .filter(|i| filter.as_ref().map_or(true, |f| &i.status == f))
        .map(|i| IssueSummary {
            id: i.id,
            title: i.title,
            status: i.status,
            claimed_by: i.claimed_by,
        })
        .collect();

    output_success(IssueListData { issues: summaries });
}

fn cmd_show(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let issue = find_issue(&issues, &id);

    output_success(IssueData { issue });
}

fn cmd_context(max_tokens: usize) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Build context blob
    let mut context = String::new();
    context.push_str("# Manna Context\n\n");

    // Separate issues by status
    let open: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::Open)
        .collect();
    let in_progress: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::InProgress)
        .collect();
    let blocked: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::Blocked)
        .collect();

    // Open issues
    context.push_str(&format!("## Open Issues ({})\n", open.len()));
    for issue in &open {
        context.push_str(&format!("- {}: {} [open]\n", issue.id, issue.title));
    }
    context.push('\n');

    // In-progress issues
    context.push_str(&format!("## In Progress Issues ({})\n", in_progress.len()));
    for issue in &in_progress {
        let claimed = issue
            .claimed_by
            .as_ref()
            .map_or("".to_string(), |s| format!(", claimed by {}", s));
        context.push_str(&format!(
            "- {}: {} [in_progress{}]\n",
            issue.id, issue.title, claimed
        ));
    }
    context.push('\n');

    // Blocked issues
    context.push_str(&format!("## Blocked Issues ({})\n", blocked.len()));
    for issue in &blocked {
        let blockers = issue.blocked_by.join(", ");
        context.push_str(&format!(
            "- {}: {} [blocked by: {}]\n",
            issue.id, issue.title, blockers
        ));
    }

    // Truncate if needed (rough estimate: 1 token ≈ 4 chars)
    let max_chars = max_tokens * 4;
    if context.len() > max_chars {
        context.truncate(max_chars - 20);
        context.push_str("\n\n[truncated]");
    }

    output_success(ContextData { context });
}

// ============================================================================
// Main Entry Point
// ============================================================================

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Init => cmd_init(),
        Commands::Status => cmd_status(),
        Commands::Create { title, description } => cmd_create(title, description),
        Commands::Claim { id } => cmd_claim(id),
        Commands::Done { id } => cmd_done(id),
        Commands::Abandon { id } => cmd_abandon(id),
        Commands::Block { id, blocker_id } => cmd_block(id, blocker_id),
        Commands::Unblock { id, blocker_id } => cmd_unblock(id, blocker_id),
        Commands::List { status } => cmd_list(status),
        Commands::Show { id } => cmd_show(id),
        Commands::Context { max_tokens } => cmd_context(max_tokens),
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    // Mutex to serialize tests that modify MANNA_SESSION_ID env var
    static ENV_MUTEX: Mutex<()> = Mutex::new(());

    fn setup_store() -> (TempDir, MannaStore) {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());
        store.init().unwrap();
        (temp_dir, store)
    }

    #[test]
    fn test_get_session_id_default() {
        let _lock = ENV_MUTEX.lock().unwrap();
        // Clear env var if set
        std::env::remove_var("MANNA_SESSION_ID");

        let session_id = get_session_id();
        assert!(session_id.starts_with("ses_pid"));
    }

    #[test]
    fn test_get_session_id_from_env() {
        let _lock = ENV_MUTEX.lock().unwrap();
        std::env::set_var("MANNA_SESSION_ID", "ses_test_123");
        let session_id = get_session_id();
        assert_eq!(session_id, "ses_test_123");
        std::env::remove_var("MANNA_SESSION_ID");
    }

    #[test]
    fn test_parse_status_valid() {
        assert_eq!(parse_status("open").unwrap(), IssueStatus::Open);
        assert_eq!(
            parse_status("in_progress").unwrap(),
            IssueStatus::InProgress
        );
        assert_eq!(parse_status("blocked").unwrap(), IssueStatus::Blocked);
        assert_eq!(parse_status("done").unwrap(), IssueStatus::Done);
        // Case insensitive
        assert_eq!(parse_status("OPEN").unwrap(), IssueStatus::Open);
        assert_eq!(
            parse_status("In_Progress").unwrap(),
            IssueStatus::InProgress
        );
    }

    #[test]
    fn test_parse_status_invalid() {
        let result = parse_status("invalid");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid status"));
    }

    #[test]
    fn test_error_to_exit_code_user_errors() {
        assert_eq!(
            error_to_exit_code(&MannaError::IssueNotFound("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::IssueAlreadyExists("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::InvalidId("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::NotInitialized),
            EXIT_USER_ERROR
        );
    }

    #[test]
    fn test_error_to_exit_code_system_errors() {
        assert_eq!(
            error_to_exit_code(&MannaError::LockFailed("x".to_string())),
            EXIT_SYSTEM_ERROR
        );
    }

    #[test]
    fn test_find_issue_found() {
        let issues = vec![
            Issue::new("mn-abc123".to_string(), "Test 1".to_string()).unwrap(),
            Issue::new("mn-def456".to_string(), "Test 2".to_string()).unwrap(),
        ];

        let found = find_issue(&issues, "mn-def456");
        assert_eq!(found.id, "mn-def456");
        assert_eq!(found.title, "Test 2");
    }

    #[test]
    fn test_issue_summary_serialization() {
        let summary = IssueSummary {
            id: "mn-abc123".to_string(),
            title: "Test".to_string(),
            status: IssueStatus::Open,
            claimed_by: None,
        };

        let yaml = serde_yaml::to_string(&summary).unwrap();
        assert!(yaml.contains("id: mn-abc123"));
        assert!(yaml.contains("title: Test"));
        assert!(yaml.contains("status: open"));
        // claimed_by should be skipped when None
        assert!(!yaml.contains("claimed_by"));
    }

    #[test]
    fn test_issue_summary_with_claimed_by() {
        let summary = IssueSummary {
            id: "mn-abc123".to_string(),
            title: "Test".to_string(),
            status: IssueStatus::InProgress,
            claimed_by: Some("ses_123".to_string()),
        };

        let yaml = serde_yaml::to_string(&summary).unwrap();
        assert!(yaml.contains("claimed_by: ses_123"));
    }

    #[test]
    fn test_success_response_serialization() {
        let response = SuccessResponse {
            success: true,
            data: InitData {
                initialized: true,
                path: ".manna".to_string(),
            },
        };

        let yaml = serde_yaml::to_string(&response).unwrap();
        assert!(yaml.contains("success: true"));
        assert!(yaml.contains("initialized: true"));
        assert!(yaml.contains("path: .manna"));
    }

    #[test]
    fn test_error_response_serialization() {
        let response = ErrorResponse {
            success: false,
            error: "Test error".to_string(),
        };

        let yaml = serde_yaml::to_string(&response).unwrap();
        assert!(yaml.contains("success: false"));
        assert!(yaml.contains("error: Test error"));
    }

    // Integration tests using temp directory
    #[test]
    fn test_store_init_and_load() {
        let (_temp_dir, store) = setup_store();

        assert!(store.is_initialized());
        let issues = store.load_issues().unwrap();
        assert!(issues.is_empty());
    }

    #[test]
    fn test_create_and_retrieve_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-test01".to_string(), "Test Issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].id, "mn-test01");
        assert_eq!(issues[0].title, "Test Issue");
    }

    #[test]
    fn test_claim_and_release_workflow() {
        let (_temp_dir, store) = setup_store();

        let mut issue = Issue::new("mn-claim1".to_string(), "Claim Test".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        // Claim
        issue.claim("ses_test".to_string()).unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::InProgress);
        assert_eq!(issues[0].claimed_by, Some("ses_test".to_string()));

        // Release
        issue.release().unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::Open);
        assert!(issues[0].claimed_by.is_none());
    }

    #[test]
    fn test_complete_workflow() {
        let (_temp_dir, store) = setup_store();

        let mut issue = Issue::new("mn-done01".to_string(), "Complete Test".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        issue.claim("ses_test".to_string()).unwrap();
        store.update_issue(&issue).unwrap();

        issue.complete().unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::Done);
    }

    #[test]
    fn test_block_workflow() {
        let (_temp_dir, store) = setup_store();

        let blocker = Issue::new("mn-block1".to_string(), "Blocker".to_string()).unwrap();
        store.append_issue(&blocker).unwrap();

        let mut issue = Issue::new("mn-block2".to_string(), "Blocked Issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        issue.add_blocker("mn-block1".to_string());
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        let blocked_issue = issues.iter().find(|i| i.id == "mn-block2").unwrap();
        assert_eq!(blocked_issue.status, IssueStatus::Blocked);
        assert!(blocked_issue.blocked_by.contains(&"mn-block1".to_string()));
    }

    #[test]
    fn test_unblock_workflow() {
        let (_temp_dir, store) = setup_store();

        let blocker = Issue::new("mn-unblk1".to_string(), "Blocker".to_string()).unwrap();
        store.append_issue(&blocker).unwrap();

        let mut issue = Issue::new("mn-unblk2".to_string(), "Blocked".to_string()).unwrap();
        issue.add_blocker("mn-unblk1".to_string());
        store.append_issue(&issue).unwrap();

        issue.remove_blocker("mn-unblk1");
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        let unblocked = issues.iter().find(|i| i.id == "mn-unblk2").unwrap();
        assert_eq!(unblocked.status, IssueStatus::Open);
        assert!(unblocked.blocked_by.is_empty());
    }

    #[test]
    fn test_context_generation() {
        let issues = vec![
            Issue::new("mn-ctx001".to_string(), "Open Issue".to_string()).unwrap(),
            {
                let mut i = Issue::new("mn-ctx002".to_string(), "In Progress".to_string()).unwrap();
                i.claim("ses_test".to_string()).unwrap();
                i
            },
            {
                let mut i =
                    Issue::new("mn-ctx003".to_string(), "Blocked Issue".to_string()).unwrap();
                i.add_blocker("mn-ctx001".to_string());
                i
            },
        ];

        // Verify structure
        let open: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Open)
            .collect();
        let in_progress: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::InProgress)
            .collect();
        let blocked: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Blocked)
            .collect();

        assert_eq!(open.len(), 1);
        assert_eq!(in_progress.len(), 1);
        assert_eq!(blocked.len(), 1);
    }

    #[test]
    fn test_list_filtering() {
        let issues = vec![
            Issue::new("mn-flt001".to_string(), "Open 1".to_string()).unwrap(),
            Issue::new("mn-flt002".to_string(), "Open 2".to_string()).unwrap(),
            {
                let mut i = Issue::new("mn-flt003".to_string(), "Done".to_string()).unwrap();
                i.claim("ses".to_string()).unwrap();
                i.complete().unwrap();
                i
            },
        ];

        let open_only: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Open)
            .collect();
        assert_eq!(open_only.len(), 2);

        let done_only: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Done)
            .collect();
        assert_eq!(done_only.len(), 1);
    }
}
