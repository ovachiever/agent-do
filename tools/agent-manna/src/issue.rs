//! Issue data structures and operations.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Issue status enum matching SCHEMA.md
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IssueStatus {
    Open,
    InProgress,
    Blocked,
    Done,
}

impl Default for IssueStatus {
    fn default() -> Self {
        IssueStatus::Open
    }
}

impl std::fmt::Display for IssueStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IssueStatus::Open => write!(f, "open"),
            IssueStatus::InProgress => write!(f, "in_progress"),
            IssueStatus::Blocked => write!(f, "blocked"),
            IssueStatus::Done => write!(f, "done"),
        }
    }
}

/// An issue in Manna.
///
/// See SCHEMA.md for field definitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Issue {
    /// Unique identifier (format: mn-{6-hex})
    pub id: String,

    /// Issue title/summary (1-500 characters)
    pub title: String,

    /// Current issue state
    pub status: IssueStatus,

    /// Optional detailed description
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// When issue was created
    pub created_at: DateTime<Utc>,

    /// Last modification time
    pub updated_at: DateTime<Utc>,

    /// Issues blocking this one
    #[serde(default)]
    pub blocked_by: Vec<String>,

    /// Session ID of who is working on this
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claimed_by: Option<String>,

    /// When it was claimed
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claimed_at: Option<DateTime<Utc>>,
}

impl Issue {
    /// Create a new issue with the given ID and title.
    ///
    /// # Arguments
    /// * `id` - Unique issue identifier (format: mn-{6-hex})
    /// * `title` - Issue title (1-500 characters)
    ///
    /// # Returns
    /// Result with new Issue or validation error
    pub fn new(id: String, title: String) -> Result<Self, String> {
        if title.is_empty() || title.len() > 500 {
            return Err(format!(
                "Title must be 1-500 characters, got {}",
                title.len()
            ));
        }

        let now = Utc::now();
        Ok(Issue {
            id,
            title,
            status: IssueStatus::Open,
            description: None,
            created_at: now,
            updated_at: now,
            blocked_by: Vec::new(),
            claimed_by: None,
            claimed_at: None,
        })
    }

    /// Claim this issue for a session
    ///
    /// # Arguments
    /// * `session_id` - Session identifier claiming the issue
    ///
    /// # Returns
    /// Result indicating success or error if already claimed
    pub fn claim(&mut self, session_id: String) -> Result<(), String> {
        if self.status != IssueStatus::Open {
            return Err(format!(
                "Cannot claim issue with status '{}', must be 'open'",
                self.status
            ));
        }

        if self.claimed_by.is_some() {
            return Err("Issue is already claimed".to_string());
        }

        let now = Utc::now();
        self.claimed_by = Some(session_id);
        self.claimed_at = Some(now);
        self.status = IssueStatus::InProgress;
        self.updated_at = now;

        Ok(())
    }

    /// Release (abandon) this issue
    ///
    /// # Returns
    /// Result indicating success or error if not claimed
    pub fn release(&mut self) -> Result<(), String> {
        if self.claimed_by.is_none() {
            return Err("Issue is not claimed".to_string());
        }

        if self.status != IssueStatus::InProgress {
            return Err(format!(
                "Cannot release issue with status '{}', must be 'in_progress'",
                self.status
            ));
        }

        self.claimed_by = None;
        self.claimed_at = None;
        self.status = IssueStatus::Open;
        self.updated_at = Utc::now();

        Ok(())
    }

    /// Mark this issue as complete
    ///
    /// # Returns
    /// Result indicating success or error if not in progress
    pub fn complete(&mut self) -> Result<(), String> {
        if self.status != IssueStatus::InProgress {
            return Err(format!(
                "Cannot complete issue with status '{}', must be 'in_progress'",
                self.status
            ));
        }

        self.status = IssueStatus::Done;
        self.updated_at = Utc::now();

        Ok(())
    }

    /// Add a blocker to this issue
    ///
    /// # Arguments
    /// * `blocker_id` - ID of the blocking issue
    pub fn add_blocker(&mut self, blocker_id: String) {
        if !self.blocked_by.contains(&blocker_id) {
            self.blocked_by.push(blocker_id);
            self.update_blocked_status();
            self.updated_at = Utc::now();
        }
    }

    /// Remove a blocker from this issue
    ///
    /// # Arguments
    /// * `blocker_id` - ID of the blocking issue to remove
    pub fn remove_blocker(&mut self, blocker_id: &str) {
        if let Some(pos) = self.blocked_by.iter().position(|id| id == blocker_id) {
            self.blocked_by.remove(pos);
            self.update_blocked_status();
            self.updated_at = Utc::now();
        }
    }

    /// Update blocked status based on blocked_by list
    fn update_blocked_status(&mut self) {
        if !self.blocked_by.is_empty() && self.status != IssueStatus::Done {
            self.status = IssueStatus::Blocked;
        } else if self.blocked_by.is_empty() && self.status == IssueStatus::Blocked {
            self.status = if self.claimed_by.is_some() {
                IssueStatus::InProgress
            } else {
                IssueStatus::Open
            };
        }
    }

    /// Validate issue data integrity
    pub fn validate(&self) -> Result<(), String> {
        if self.title.is_empty() || self.title.len() > 500 {
            return Err(format!(
                "Title must be 1-500 characters, got {}",
                self.title.len()
            ));
        }

        if !self.id.starts_with("mn-") {
            return Err(format!("ID must start with 'mn-', got '{}'", self.id));
        }

        if self.status == IssueStatus::InProgress && self.claimed_by.is_none() {
            return Err("Issue in_progress must have claimed_by set".to_string());
        }

        if self.claimed_by.is_some() && self.claimed_at.is_none() {
            return Err("Issue with claimed_by must have claimed_at set".to_string());
        }

        if self.claimed_by.is_none() && self.claimed_at.is_some() {
            return Err("Issue without claimed_by cannot have claimed_at set".to_string());
        }

        Ok(())
    }
}

/// Session event types matching SCHEMA.md
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionEventType {
    Start,
    Claim,
    Release,
    Done,
    End,
}

impl std::fmt::Display for SessionEventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SessionEventType::Start => write!(f, "start"),
            SessionEventType::Claim => write!(f, "claim"),
            SessionEventType::Release => write!(f, "release"),
            SessionEventType::Done => write!(f, "done"),
            SessionEventType::End => write!(f, "end"),
        }
    }
}

/// A session event in the session log.
///
/// See SCHEMA.md for field definitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvent {
    /// Session identifier
    pub session_id: String,

    /// Event type
    pub event: SessionEventType,

    /// When event occurred
    pub timestamp: DateTime<Utc>,

    /// Issue ID (required for claim, release, done events)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issue_id: Option<String>,

    /// Context data (required for start, end events)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub context: Option<serde_json::Value>,
}

impl SessionEvent {
    /// Create a new session start event.
    pub fn start(session_id: String, context: serde_json::Value) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Start,
            timestamp: Utc::now(),
            issue_id: None,
            context: Some(context),
        }
    }

    /// Create a new claim event.
    pub fn claim(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Claim,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new release event.
    pub fn release(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Release,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new done event.
    pub fn done(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Done,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new session end event.
    pub fn end(session_id: String, context: serde_json::Value) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::End,
            timestamp: Utc::now(),
            issue_id: None,
            context: Some(context),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_issue_valid() {
        let issue = Issue::new("mn-abc123".to_string(), "Test issue".to_string()).unwrap();
        assert_eq!(issue.id, "mn-abc123");
        assert_eq!(issue.title, "Test issue");
        assert_eq!(issue.status, IssueStatus::Open);
        assert!(issue.description.is_none());
        assert!(issue.blocked_by.is_empty());
        assert!(issue.claimed_by.is_none());
        assert!(issue.claimed_at.is_none());
    }

    #[test]
    fn test_new_issue_empty_title() {
        let result = Issue::new("mn-abc123".to_string(), "".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("1-500 characters"));
    }

    #[test]
    fn test_new_issue_title_too_long() {
        let long_title = "x".repeat(501);
        let result = Issue::new("mn-abc123".to_string(), long_title);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("1-500 characters"));
    }

    #[test]
    fn test_claim_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.claim("ses_123".to_string());
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::InProgress);
        assert_eq!(issue.claimed_by, Some("ses_123".to_string()));
        assert!(issue.claimed_at.is_some());
    }

    #[test]
    fn test_claim_already_claimed() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.claim("ses_456".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already claimed"));
    }

    #[test]
    fn test_claim_wrong_status() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.status = IssueStatus::Done;
        let result = issue.claim("ses_123".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must be 'open'"));
    }

    #[test]
    fn test_release_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.release();
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::Open);
        assert!(issue.claimed_by.is_none());
        assert!(issue.claimed_at.is_none());
    }

    #[test]
    fn test_release_not_claimed() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.release();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not claimed"));
    }

    #[test]
    fn test_complete_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.complete();
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::Done);
    }

    #[test]
    fn test_complete_not_in_progress() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.complete();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must be 'in_progress'"));
    }

    #[test]
    fn test_add_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.blocked_by.len(), 1);
        assert_eq!(issue.status, IssueStatus::Blocked);
    }

    #[test]
    fn test_add_duplicate_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.blocked_by.len(), 1);
    }

    #[test]
    fn test_remove_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        issue.remove_blocker("mn-def456");
        assert!(issue.blocked_by.is_empty());
        assert_eq!(issue.status, IssueStatus::Open);
    }

    #[test]
    fn test_blocked_status_with_claim() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        assert_eq!(issue.status, IssueStatus::InProgress);

        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.status, IssueStatus::Blocked);

        issue.remove_blocker("mn-def456");
        assert_eq!(issue.status, IssueStatus::InProgress);
    }

    #[test]
    fn test_validate_valid_issue() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        assert!(issue.validate().is_ok());
    }

    #[test]
    fn test_validate_in_progress_without_claim() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.status = IssueStatus::InProgress;
        let result = issue.validate();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must have claimed_by"));
    }

    #[test]
    fn test_serde_roundtrip() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let json = serde_json::to_string(&issue).unwrap();
        let deserialized: Issue = serde_json::from_str(&json).unwrap();
        assert_eq!(issue.id, deserialized.id);
        assert_eq!(issue.title, deserialized.title);
        assert_eq!(issue.status, deserialized.status);
    }

    #[test]
    fn test_status_serialization() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let json = serde_json::to_string(&issue).unwrap();
        assert!(json.contains(r#""status":"open"#));
    }
}
