//! Shared error type for the Workspace Daemon.

use std::io;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum DaemonError {
    #[error("path '{0}' escapes the workspace root")]
    PathEscape(String),

    #[error("path '{0}' is not a valid utf-8 path")]
    InvalidPath(String),

    #[error("hash mismatch: expected '{expected}', actual '{actual}'")]
    HashMismatch { expected: String, actual: String },

    #[error("file not found: {0}")]
    NotFound(String),

    #[error("io error: {0}")]
    Io(Box<io::Error>),

    #[error("git error: {0}")]
    Git(String),

    #[error("invalid argument: {0}")]
    InvalidArgument(String),

    #[error("command timed out after {0}s")]
    Timeout(u64),
}

// Manual conversion so `?` on a bare `io::Error` boxes it (keeping the enum
// small while remaining ergonomic at call sites).
impl From<io::Error> for DaemonError {
    fn from(e: io::Error) -> Self {
        DaemonError::Io(Box::new(e))
    }
}

impl DaemonError {
    /// Whether this error is a security-relevant rejection (used by tests).
    pub fn is_security_rejection(&self) -> bool {
        matches!(self, DaemonError::PathEscape(_))
    }
}

pub type Result<T> = std::result::Result<T, DaemonError>;
