//! Error types for Manna using thiserror.

use thiserror::Error;

/// Errors that can occur in Manna operations.
#[derive(Error, Debug)]
pub enum MannaError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON parsing error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Issue not found: {0}")]
    IssueNotFound(String),

    #[error("Issue already exists: {0}")]
    IssueAlreadyExists(String),

    #[error("Invalid status transition: {from} -> {to}")]
    InvalidStatusTransition { from: String, to: String },

    #[error("Storage not initialized")]
    NotInitialized,

    #[error("Lock acquisition failed: {0}")]
    LockFailed(String),

    #[error("Invalid ID format: {0}")]
    InvalidId(String),
}

pub type Result<T> = std::result::Result<T, MannaError>;
