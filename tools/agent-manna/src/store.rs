//! JSONL storage with file locking for Manna.
//!
//! Storage files:
//! - `.manna/issues.jsonl` - Issue records
//! - `.manna/sessions.jsonl` - Session event log

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use fs2::FileExt;

use crate::error::{MannaError, Result};
use crate::issue::{Issue, SessionEvent};

/// Directory name for Manna storage.
const MANNA_DIR: &str = ".manna";

/// Issues JSONL file name.
const ISSUES_FILE: &str = "issues.jsonl";

/// Sessions JSONL file name.
const SESSIONS_FILE: &str = "sessions.jsonl";

/// Manna storage backed by JSONL files.
///
/// All writes acquire exclusive file locks to prevent corruption
/// during concurrent access.
#[derive(Debug, Clone)]
pub struct MannaStore {
    /// Base directory containing `.manna/`.
    base_dir: PathBuf,
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

    /// Initialize storage by creating `.manna/` directory and JSONL files.
    ///
    /// This is idempotent - running twice does not error.
    pub fn init(&self) -> Result<()> {
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
        self.manna_dir().exists() && self.issues_path().exists() && self.sessions_path().exists()
    }

    /// Load all issues from issues.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_issues(&self) -> Result<Vec<Issue>> {
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
    pub fn append_issue(&self, issue: &Issue) -> Result<()> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
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

    /// Update an existing issue by rewriting the entire file atomically.
    ///
    /// Writes to a temp file then renames to prevent corruption.
    pub fn update_issue(&self, updated_issue: &Issue) -> Result<()> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        // Load all issues
        let mut issues = self.load_issues()?;

        // Find and update the issue
        let mut found = false;
        for issue in &mut issues {
            if issue.id == updated_issue.id {
                *issue = updated_issue.clone();
                found = true;
                break;
            }
        }

        if !found {
            return Err(MannaError::IssueNotFound(updated_issue.id.clone()));
        }

        // Write to temp file
        let temp_path = path.with_extension("jsonl.tmp");
        {
            let temp_file = File::create(&temp_path)?;

            // Acquire exclusive lock on temp file
            temp_file
                .lock_exclusive()
                .map_err(|e| MannaError::LockFailed(e.to_string()))?;

            let mut writer = std::io::BufWriter::new(&temp_file);
            for issue in &issues {
                serde_json::to_writer(&mut writer, issue)?;
                writeln!(writer)?;
            }
            writer.flush()?;
        }

        // Atomic rename
        fs::rename(&temp_path, &path)?;

        Ok(())
    }

    /// Load all session events from sessions.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_sessions(&self) -> Result<Vec<SessionEvent>> {
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
    use std::sync::Arc;
    use std::thread;
    use tempfile::TempDir;

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
    fn test_append_and_load_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-abc123".to_string(), "Test issue".to_string());
        store.append_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].id, "mn-abc123");
        assert_eq!(issues[0].title, "Test issue");
    }

    #[test]
    fn test_append_multiple_issues() {
        let (_temp_dir, store) = setup_store();

        let issue1 = Issue::new("mn-111111".to_string(), "First".to_string());
        let issue2 = Issue::new("mn-222222".to_string(), "Second".to_string());
        let issue3 = Issue::new("mn-333333".to_string(), "Third".to_string());

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

        let mut issue = Issue::new("mn-update".to_string(), "Original".to_string());
        store.append_issue(&issue).unwrap();

        issue.title = "Updated".to_string();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].title, "Updated");
    }

    #[test]
    fn test_update_nonexistent_issue_fails() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-ghost".to_string(), "Ghost".to_string());

        let result = store.update_issue(&issue);
        assert!(matches!(result, Err(MannaError::IssueNotFound(_))));
    }

    #[test]
    fn test_skip_malformed_lines() {
        let (_temp_dir, store) = setup_store();

        // Write a valid issue
        let issue = Issue::new("mn-valid".to_string(), "Valid".to_string());
        store.append_issue(&issue).unwrap();

        // Manually append a malformed line
        let path = store.issues_path();
        let mut file = OpenOptions::new().append(true).open(&path).unwrap();
        writeln!(file, "{{not valid json").unwrap();

        // Append another valid issue
        let issue2 = Issue::new("mn-valid2".to_string(), "Valid2".to_string());
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
                    );
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
    fn test_not_initialized_errors() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        // Don't call init()

        let result = store.load_issues();
        assert!(matches!(result, Err(MannaError::NotInitialized)));

        let issue = Issue::new("mn-test".to_string(), "Test".to_string());
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
