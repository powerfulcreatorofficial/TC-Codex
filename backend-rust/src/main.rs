//! Engineering TC Workspace Daemon — gRPC server entrypoint.
//!
//! The daemon binds a gRPC server on `127.0.0.1:50051` (override with
//! `TC_DAEMON_ADDR`) and confines all filesystem access to the workspace root
//! configured via `TC_WORKSPACE_ROOT`.

// Allow the clippy lints that fire on tonic-generated code.
#![allow(clippy::result_large_err, clippy::type_complexity)]

use std::net::SocketAddr;
use std::path::PathBuf;
use tc_backend::grpc::{health_server, WorkspaceDaemonService};
use tc_backend::{Daemon, Redactor, Workspace};
use tonic::transport::Server;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Resolve the workspace root. This must be provided explicitly — there is
    // no default, so the daemon can never accidentally operate on the host.
    let root = std::env::var("TC_WORKSPACE_ROOT")
        .map(PathBuf::from)
        .expect("TC_WORKSPACE_ROOT must be set to the workspace root");
    let workspace =
        Workspace::new(&root).map_err(|e| format!("invalid workspace root {root:?}: {e}"))?;

    // Build a redactor seeded with secret *values* from the daemon's own
    // environment. Only variables whose name looks like a secret are seeded,
    // so ordinary config (PATH, etc.) is not treated as a secret. The values
    // are used to scrub literal occurrences in command output.
    let redactor = Redactor::new().add_env_pairs(
        std::env::vars()
            .filter(|(k, _)| is_secret_env_name(k))
            .map(|(k, v)| format!("{k}={v}"))
            .collect::<Vec<_>>()
            .iter()
            .map(|s| s.as_str()),
    );

    let daemon = Daemon::new(workspace, redactor);

    let addr_str = std::env::var("TC_DAEMON_ADDR").unwrap_or_else(|_| "127.0.0.1:50051".into());
    let addr: SocketAddr = addr_str.parse().expect("invalid TC_DAEMON_ADDR");

    let ws_root = daemon.workspace().root().to_path_buf();
    let daemon_svc = WorkspaceDaemonService::new(daemon).into_server();
    let health_svc = health_server();

    eprintln!("engineering-tc workspace daemon listening on {addr}");
    eprintln!("workspace root: {}", ws_root.display());

    Server::builder()
        .add_service(daemon_svc)
        .add_service(health_svc)
        .serve(addr)
        .await?;

    Ok(())
}

/// Heuristic: does an env var name look like it holds a secret?
fn is_secret_env_name(name: &str) -> bool {
    let upper = name.to_ascii_uppercase();
    upper.contains("TOKEN")
        || upper.contains("SECRET")
        || upper.contains("PASSWORD")
        || upper.contains("PASSWD")
        || upper.contains("API_KEY")
        || upper.contains("APIKEY")
        || upper.contains("PRIVATE_KEY")
        || upper.contains("ACCESS_KEY")
        || upper.contains("CREDENTIAL")
}
