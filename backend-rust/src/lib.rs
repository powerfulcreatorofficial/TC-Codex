//! Engineering TC Workspace Daemon library.
//!
//! The daemon exposes a gRPC API for confined filesystem reads/writes, sandboxed
//! command execution, deterministic secret redaction, and safe git operations.
//! All filesystem access is confined to a single configured workspace root.

// The tonic-generated protobuf code returns `Result<_, tonic::Status>` and
// uses complex generated types; silence the two clippy lints that fire on
// generated code we cannot edit.
#![allow(clippy::result_large_err, clippy::type_complexity)]

pub mod daemon;
pub mod error;
pub mod grpc;
pub mod redaction;
pub mod workspace;

pub use daemon::Daemon;
pub use error::DaemonError;
pub use redaction::Redactor;
pub use workspace::Workspace;
