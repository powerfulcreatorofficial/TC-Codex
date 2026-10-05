//! gRPC integration test: boot the daemon server and exercise the health
//! endpoint and a workspace-confined RPC over a real TCP socket.
//!
//! This proves the tonic/protobuf wiring compiles, binds, and serves.

use tc_backend::grpc::{daemon_proto, health_proto, WorkspaceDaemonService};
use tc_backend::{Daemon, Redactor, Workspace};
use tonic::transport::Server;

/// Pick an ephemeral free port for the test server.
fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn grpc_health_and_read_file_roundtrip() {
    use health_proto::health_client::HealthClient;
    use health_proto::HealthCheckRequest;

    let tmp = tempfile::tempdir().unwrap();
    // Seed a file to read back over gRPC.
    std::fs::write(tmp.path().join("hello.txt"), b"hi from daemon").unwrap();

    let ws = Workspace::new(tmp.path()).unwrap();
    let daemon = Daemon::new(ws, Redactor::new());
    let daemon_svc = WorkspaceDaemonService::new(daemon).into_server();
    let health_svc = tc_backend::grpc::health_server();

    let port = free_port();
    let addr: std::net::SocketAddr = format!("127.0.0.1:{port}").parse().unwrap();

    let server = tokio::spawn(async move {
        Server::builder()
            .add_service(daemon_svc)
            .add_service(health_svc)
            .serve(addr)
            .await
            .unwrap();
    });

    // Give the server a moment to bind.
    tokio::time::sleep(std::time::Duration::from_millis(150)).await;

    let endpoint = tonic::transport::Channel::from_shared(format!("http://127.0.0.1:{port}"))
        .unwrap()
        .connect()
        .await
        .unwrap();

    // 1) Health check returns SERVING.
    let mut health = HealthClient::new(endpoint.clone());
    let resp = health
        .check(HealthCheckRequest {
            service: String::new(),
        })
        .await
        .unwrap()
        .into_inner();
    assert_eq!(
        resp.status,
        health_proto::health_check_response::ServingStatus::Serving as i32
    );

    // 2) Read a file over gRPC and confirm confinement + hashing.
    use daemon_proto::workspace_daemon_client::WorkspaceDaemonClient;
    use daemon_proto::ReadFileRequest;
    let mut client = WorkspaceDaemonClient::new(endpoint);
    let resp = client
        .read_file(ReadFileRequest {
            path: "hello.txt".into(),
            offset: 0,
            length: 0,
        })
        .await
        .unwrap()
        .into_inner();
    assert_eq!(resp.content, b"hi from daemon");
    assert_eq!(
        resp.sha256,
        tc_backend::daemon::sha256_hex(b"hi from daemon")
    );

    // 3) Path traversal is rejected with PERMISSION_DENIED.
    let err = client
        .read_file(ReadFileRequest {
            path: "../../etc/passwd".into(),
            offset: 0,
            length: 0,
        })
        .await
        .unwrap_err();
    assert_eq!(err.code(), tonic::Code::PermissionDenied);

    server.abort();
    let _ = server.await;
}
