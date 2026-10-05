//! gRPC service implementation: a thin adapter over `daemon::Daemon`.

// The protobuf-generated trait impls return `Result<_, tonic::Status>` and
// `tonic::Status` is large; allow the generated code's large-err lint.
#![allow(clippy::result_large_err, clippy::type_complexity)]

pub mod daemon_proto {
    tonic::include_proto!("tc.daemon.v1");
}

pub mod health_proto {
    tonic::include_proto!("grpc.health.v1");
}

use crate::daemon::{Daemon, ExecResult, ReadResult, WriteResult};
use crate::error::DaemonError;
use daemon_proto::workspace_daemon_server::{
    WorkspaceDaemon as WorkspaceDaemonTrait, WorkspaceDaemonServer,
};
use daemon_proto::*;
use health_proto::health_server::{Health, HealthServer};
use health_proto::*;
use tonic::{Request, Response, Status};

/// Convert a DaemonError into a gRPC Status.
pub fn to_status(e: DaemonError) -> Status {
    match e {
        DaemonError::PathEscape(p) => {
            Status::permission_denied(format!("path escapes workspace: {p}"))
        }
        DaemonError::NotFound(p) => Status::not_found(format!("not found: {p}")),
        DaemonError::HashMismatch { expected, actual } => Status::failed_precondition(format!(
            "hash mismatch: expected={expected} actual={actual}"
        )),
        DaemonError::InvalidArgument(msg) => Status::invalid_argument(msg),
        DaemonError::Timeout(secs) => {
            Status::deadline_exceeded(format!("command timed out after {secs}s"))
        }
        other => Status::internal(other.to_string()),
    }
}

pub struct WorkspaceDaemonService {
    daemon: Daemon,
}

impl WorkspaceDaemonService {
    pub fn new(daemon: Daemon) -> Self {
        Self { daemon }
    }

    pub fn into_server(self) -> WorkspaceDaemonServer<Self> {
        WorkspaceDaemonServer::new(self)
    }
}

#[tonic::async_trait]
impl WorkspaceDaemonTrait for WorkspaceDaemonService {
    async fn read_file(
        &self,
        req: Request<ReadFileRequest>,
    ) -> Result<Response<ReadFileResponse>, Status> {
        let req = req.into_inner();
        let ReadResult {
            content,
            sha256,
            total_size,
            truncated,
        } = self
            .daemon
            .read_file(&req.path, req.offset, req.length)
            .map_err(to_status)?;
        Ok(Response::new(ReadFileResponse {
            content,
            sha256,
            total_size,
            truncated,
        }))
    }

    async fn write_file(
        &self,
        req: Request<WriteFileRequest>,
    ) -> Result<Response<WriteFileResponse>, Status> {
        let req = req.into_inner();
        let WriteResult { sha256, written } = self
            .daemon
            .write_file(&req.path, &req.content, &req.expected_hash)
            .map_err(to_status)?;
        Ok(Response::new(WriteFileResponse { sha256, written }))
    }

    async fn exec_command(
        &self,
        req: Request<ExecCommandRequest>,
    ) -> Result<Response<ExecCommandResponse>, Status> {
        let req = req.into_inner();
        let ExecResult {
            exit_code,
            status,
            stdout,
            stderr,
            duration_ms,
        } = self
            .daemon
            .exec_command(&req.argv, req.timeout_seconds)
            .await
            .map_err(to_status)?;
        Ok(Response::new(ExecCommandResponse {
            exit_code,
            status,
            stdout,
            stderr,
            duration_ms,
        }))
    }

    async fn git_create_branch(
        &self,
        req: Request<GitCreateBranchRequest>,
    ) -> Result<Response<GitCreateBranchResponse>, Status> {
        let req = req.into_inner();
        let (branch_name, message) = self
            .daemon
            .git_create_branch(&req.branch_name, req.from_head)
            .map_err(to_status)?;
        Ok(Response::new(GitCreateBranchResponse {
            branch_name,
            created: true,
            message,
        }))
    }

    async fn git_status(
        &self,
        req: Request<GitStatusRequest>,
    ) -> Result<Response<GitStatusResponse>, Status> {
        let _req = req.into_inner();
        let (branch, clean, entries) = self.daemon.git_status().map_err(to_status)?;
        let entries = entries
            .into_iter()
            .map(|(path, status)| GitStatusEntry { path, status })
            .collect();
        Ok(Response::new(GitStatusResponse {
            branch,
            clean,
            entries,
        }))
    }

    async fn git_commit(
        &self,
        req: Request<GitCommitRequest>,
    ) -> Result<Response<GitCommitResponse>, Status> {
        let req = req.into_inner();
        let (commit_hash, message) = self
            .daemon
            .git_commit(&req.message, &req.paths)
            .map_err(to_status)?;
        let committed = message == "committed";
        Ok(Response::new(GitCommitResponse {
            commit_hash,
            committed,
            message,
        }))
    }
}

/// Minimal gRPC health service: always SERVING once constructed.
pub struct HealthService;

#[tonic::async_trait]
impl Health for HealthService {
    async fn check(
        &self,
        _req: Request<HealthCheckRequest>,
    ) -> Result<Response<HealthCheckResponse>, Status> {
        Ok(Response::new(HealthCheckResponse {
            status: health_check_response::ServingStatus::Serving as i32,
        }))
    }
}

pub fn health_server() -> HealthServer<HealthService> {
    HealthServer::new(HealthService)
}
