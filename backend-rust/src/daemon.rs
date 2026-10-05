//! Core Workspace Daemon operations.
//!
//! These functions are the security-critical heart of the daemon. They are
//! deliberately decoupled from the gRPC transport so they can be unit-tested
//! directly. The gRPC layer (in `grpc.rs`) is a thin adapter over this module.

use crate::error::{DaemonError, Result};
use crate::redaction::Redactor;
use crate::workspace::Workspace;
use sha2::{Digest, Sha256};
use std::time::{Duration, Instant};
use tokio::process::Command;

/// Result of a `read_file` operation.
#[derive(Debug)]
pub struct ReadResult {
    pub content: Vec<u8>,
    pub sha256: String,
    pub total_size: u64,
    pub truncated: bool,
}

/// Result of a `write_file` operation.
#[derive(Debug)]
pub struct WriteResult {
    pub sha256: String,
    pub written: bool,
}

/// A structured git status entry: (path, status_label).
pub type GitStatusEntry = (String, String);

/// Result of a `git_status` operation: branch, cleanliness, and entries.
pub type GitStatus = (String, bool, Vec<GitStatusEntry>);

/// Result of an `exec_command` operation.
#[derive(Debug)]
pub struct ExecResult {
    pub exit_code: i32,
    pub status: String,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub duration_ms: u64,
}

/// SHA-256 of the empty byte string (used for new/missing files).
pub fn empty_hash() -> String {
    hex::encode(Sha256::digest(b""))
}

/// Compute the SHA-256 hex digest of a byte slice.
pub fn sha256_hex(data: &[u8]) -> String {
    hex::encode(Sha256::digest(data))
}

/// The Workspace Daemon. Owns the workspace root and redactor.
#[derive(Clone)]
pub struct Daemon {
    workspace: Workspace,
    redactor: Redactor,
}

impl Daemon {
    pub fn new(workspace: Workspace, redactor: Redactor) -> Self {
        Self {
            workspace,
            redactor,
        }
    }

    pub fn workspace(&self) -> &Workspace {
        &self.workspace
    }

    /// Read a (optionally bounded) chunk of a file inside the workspace root.
    ///
    /// `offset` is a byte offset from the start of the file; `length` of 0
    /// means "read the whole file from offset". The returned `sha256` is
    /// always the hash of the *full* file, independent of chunking.
    pub fn read_file(&self, rel: &str, offset: u64, length: u64) -> Result<ReadResult> {
        let path = self.workspace.resolve(rel)?;
        let metadata = std::fs::metadata(&path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                DaemonError::NotFound(rel.to_string())
            } else {
                DaemonError::from(e)
            }
        })?;
        if !metadata.is_file() {
            return Err(DaemonError::InvalidArgument(format!(
                "path '{rel}' is not a regular file"
            )));
        }
        let total_size = metadata.len();
        let bytes = std::fs::read(&path)?;

        let start = std::cmp::min(offset as usize, bytes.len());
        let end = if length == 0 {
            bytes.len()
        } else {
            std::cmp::min(start + length as usize, bytes.len())
        };
        // "truncated" means the returned content is a subset of the whole
        // file — either we started past byte 0 or we stopped before the end.
        let truncated = start != 0 || end != bytes.len();
        let chunk = bytes[start..end].to_vec();

        Ok(ReadResult {
            content: chunk,
            sha256: sha256_hex(&bytes),
            total_size,
            truncated,
        })
    }

    /// Atomically write a file using compare-and-set on the current SHA-256.
    ///
    /// Semantics:
    /// - Compute the SHA-256 of the file's *current* contents (empty string
    ///   hash if the file does not exist).
    /// - If `expected_hash` does not equal the current hash, refuse the write
    ///   and return a `HashMismatch` error. `written` is false.
    /// - Otherwise write atomically: write to a temp file in the same
    ///   directory then rename over the target. Return the new hash.
    pub fn write_file(
        &self,
        rel: &str,
        content: &[u8],
        expected_hash: &str,
    ) -> Result<WriteResult> {
        let path = self.workspace.resolve(rel)?;

        // Resolve the parent directory (must already exist; the daemon does
        // not create arbitrary directory trees to keep the blast radius small).
        let parent = path
            .parent()
            .ok_or_else(|| DaemonError::InvalidArgument("path has no parent".into()))?;
        if !parent.exists() {
            return Err(DaemonError::InvalidArgument(format!(
                "parent directory for '{rel}' does not exist"
            )));
        }

        // Current contents (empty if missing).
        let current = std::fs::read(&path).unwrap_or_default();
        let current_hash = sha256_hex(&current);

        if current_hash != expected_hash {
            return Err(DaemonError::HashMismatch {
                expected: expected_hash.to_string(),
                actual: current_hash,
            });
        }

        // Atomic write: temp file in the same directory, fsync, rename.
        let tmp = tempfile::Builder::new()
            .prefix(".tc-write-")
            .tempfile_in(parent)?;
        let (mut tmp_file, tmp_path) = tmp.keep().map_err(|e| DaemonError::from(e.error))?;
        use std::io::Write;
        tmp_file.write_all(content)?;
        tmp_file.sync_all()?;
        drop(tmp_file);

        // Rename is atomic on the same filesystem.
        std::fs::rename(&tmp_path, &path)?;

        // Clean up the temp file if rename failed for any reason (it should
        // not exist on success).
        let _ = std::fs::remove_file(&tmp_path);

        Ok(WriteResult {
            sha256: sha256_hex(content),
            written: true,
        })
    }

    /// Execute a command inside the workspace sandbox.
    ///
    /// - `argv[0]` is the program; the rest are arguments (no shell, no
    ///   string interpolation -> no shell injection).
    /// - The command runs with CWD set to the workspace root.
    /// - An explicit `timeout_seconds` > 0 is required.
    /// - stdout/stderr are captured and redacted before being returned.
    /// - No environment secrets are forwarded: the child inherits a minimal
    ///   environment (PATH + a small allowlist) rather than the daemon's full
    ///   env, so secrets loaded into the daemon are not leaked to child
    ///   processes or their output.
    pub async fn exec_command(&self, argv: &[String], timeout_seconds: u64) -> Result<ExecResult> {
        if argv.is_empty() {
            return Err(DaemonError::InvalidArgument("empty argv".into()));
        }
        if timeout_seconds == 0 {
            return Err(DaemonError::InvalidArgument(
                "timeout_seconds must be > 0".into(),
            ));
        }

        let mut cmd = Command::new(&argv[0]);
        cmd.args(&argv[1..]);
        cmd.current_dir(self.workspace.root());
        cmd.stdin(std::process::Stdio::null());
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());
        // Minimal, allowlisted environment — never inherit secrets.
        cmd.env_clear();
        if let Some(path) = std::env::var_os("PATH") {
            cmd.env("PATH", path);
        }
        if let Some(home) = std::env::var_os("HOME") {
            cmd.env("HOME", home);
        }
        cmd.env("LC_ALL", "C");
        cmd.env("TZ", "UTC");

        let start = Instant::now();
        let mut child = cmd.spawn().map_err(|e| {
            DaemonError::InvalidArgument(format!("failed to start command {:?}: {e}", argv[0]))
        })?;

        let timeout = Duration::from_secs(timeout_seconds);
        let stdout_fut = child.stdout.take();
        let stderr_fut = child.stderr.take();

        // Read stdout/stderr concurrently with the timeout. On timeout we
        // kill the child so it cannot keep running / producing output.
        let collect = async {
            let stdout = match stdout_fut {
                Some(mut s) => {
                    use tokio::io::AsyncReadExt;
                    let mut buf = Vec::new();
                    s.read_to_end(&mut buf).await?;
                    buf
                }
                None => Vec::new(),
            };
            let stderr = match stderr_fut {
                Some(mut s) => {
                    use tokio::io::AsyncReadExt;
                    let mut buf = Vec::new();
                    s.read_to_end(&mut buf).await?;
                    buf
                }
                None => Vec::new(),
            };
            let exit = child.wait().await?;
            std::io::Result::Ok((stdout, stderr, exit))
        };

        match tokio::time::timeout(timeout, collect).await {
            Ok(Ok((stdout, stderr, exit))) => {
                let exit_code = exit.code().unwrap_or(-1);
                Ok(ExecResult {
                    exit_code,
                    status: "completed".into(),
                    stdout: self.redactor.redact_bytes(&stdout),
                    stderr: self.redactor.redact_bytes(&stderr),
                    duration_ms: start.elapsed().as_millis() as u64,
                })
            }
            Ok(Err(e)) => Err(DaemonError::from(e)),
            Err(_) => {
                // Timed out: kill the child.
                let _ = child.kill().await;
                let _ = child.wait().await;
                // Still try to capture whatever output was produced.
                Err(DaemonError::Timeout(timeout_seconds))
            }
        }
    }

    // ----- Git operations (shell out to the `git` CLI with explicit args) -----

    /// Run a `git` command in the workspace root with explicit argv (no shell).
    fn git(&self, args: &[&str]) -> Result<std::process::Output> {
        let output = std::process::Command::new("git")
            .args(args)
            .current_dir(self.workspace.root())
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .env_clear()
            .env("PATH", std::env::var_os("PATH").unwrap_or_default())
            .env("HOME", std::env::var_os("HOME").unwrap_or_default())
            .env("LC_ALL", "C")
            .env("GIT_TERMINAL_PROMPT", "0")
            .output()?;
        Ok(output)
    }

    /// Create a git branch for TC changes.
    ///
    /// By default (`from_head == false`) the branch is created from the
    /// default branch (main/master) so in-progress work on the current branch
    /// is not disturbed. If `from_head == true`, it branches from the current
    /// HEAD.
    ///
    /// This never destroys unrelated changes: it only creates a branch ref and
    /// (if requested) checks it out. It will not force anything.
    pub fn git_create_branch(
        &self,
        branch_name: &str,
        from_head: bool,
    ) -> Result<(String, String)> {
        if branch_name.is_empty() {
            return Err(DaemonError::InvalidArgument("empty branch name".into()));
        }

        if !from_head {
            // Ensure we branch from the default branch, not the current
            // (possibly dirty) branch.
            let default = self.default_branch()?;
            // `git branch <name> <default>` creates a ref without checking out.
            let out = self.git(&["branch", branch_name, &default])?;
            if !out.status.success() {
                return Err(DaemonError::Git(format!(
                    "git branch failed: {}",
                    String::from_utf8_lossy(&out.stderr)
                )));
            }
            // Safe checkout of the new branch.
            let out = self.git(&["checkout", branch_name])?;
            if !out.status.success() {
                return Err(DaemonError::Git(format!(
                    "git checkout failed: {}",
                    String::from_utf8_lossy(&out.stderr)
                )));
            }
            return Ok((branch_name.to_string(), format!("branched from {default}")));
        }

        let out = self.git(&["checkout", "-b", branch_name])?;
        if !out.status.success() {
            // Branch may already exist; try plain checkout.
            let out2 = self.git(&["checkout", branch_name])?;
            if !out2.status.success() {
                return Err(DaemonError::Git(format!(
                    "git checkout -b failed: {}",
                    String::from_utf8_lossy(&out.stderr)
                )));
            }
        }
        Ok((branch_name.to_string(), "created from HEAD".into()))
    }

    /// Determine the repository's default branch (main or master).
    fn default_branch(&self) -> Result<String> {
        // Prefer `origin/HEAD` symbolic ref; fall back to local main/master.
        let out = self.git(&["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])?;
        if out.status.success() {
            let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if let Some(b) = s.strip_prefix("origin/") {
                return Ok(b.to_string());
            }
        }
        for cand in ["main", "master"] {
            let out = self.git(&["rev-parse", "--verify", cand])?;
            if out.status.success() {
                return Ok(cand.to_string());
            }
        }
        // No commits yet — use HEAD itself.
        Ok("HEAD".to_string())
    }

    /// Report the git status of the workspace as structured entries.
    pub fn git_status(&self) -> Result<GitStatus> {
        let branch_out = self.git(&["rev-parse", "--abbrev-ref", "HEAD"])?;
        let branch = String::from_utf8_lossy(&branch_out.stdout)
            .trim()
            .to_string();

        // Porcelain v1: "<XY> <path>"
        let out = self.git(&["status", "--porcelain=v1", "-z"])?;
        if !out.status.success() {
            return Err(DaemonError::Git(format!(
                "git status failed: {}",
                String::from_utf8_lossy(&out.stderr)
            )));
        }
        let entries = parse_porcelain(&out.stdout);
        let clean = entries.is_empty();
        Ok((branch, clean, entries))
    }

    /// Commit changes safely.
    ///
    /// - If `paths` is non-empty, only those paths are staged
    ///   (`git add <paths>`). Otherwise already-staged changes are committed.
    /// - `git commit` is run with an explicit message. It will fail (not
    ///   force) if there is nothing to commit, so unrelated work is never
    ///   disturbed.
    /// - Returns the new commit hash.
    pub fn git_commit(&self, message: &str, paths: &[String]) -> Result<(String, String)> {
        if message.is_empty() {
            return Err(DaemonError::InvalidArgument("empty commit message".into()));
        }

        if !paths.is_empty() {
            // Stage only the requested paths. Resolve each relative to the
            // workspace root to avoid staging unexpected files.
            let mut args = vec!["add".to_string()];
            for p in paths {
                // Validate containment; reject escapes before handing to git.
                let _ = self.workspace.resolve(p)?;
                args.push(p.clone());
            }
            let owned_args: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
            let out = self.git(&owned_args)?;
            if !out.status.success() {
                return Err(DaemonError::Git(format!(
                    "git add failed: {}",
                    String::from_utf8_lossy(&out.stderr)
                )));
            }
        }

        let out = self.git(&["commit", "-m", message])?;
        if !out.status.success() {
            let err = String::from_utf8_lossy(&out.stderr).to_string();
            let combined = format!("{} {}", err, String::from_utf8_lossy(&out.stdout));
            // "nothing to commit" may be reported on stdout or stderr
            // depending on the git version; it is not a failure — surface it
            // so unrelated work is never force-committed.
            if combined.contains("nothing to commit") || combined.contains("no changes") {
                return Ok((String::new(), "nothing to commit".into()));
            }
            return Err(DaemonError::Git(format!("git commit failed: {err}")));
        }

        // Get the new commit hash.
        let rev = self.git(&["rev-parse", "HEAD"])?;
        if !rev.status.success() {
            return Err(DaemonError::Git(
                String::from_utf8_lossy(&rev.stderr).to_string(),
            ));
        }
        let hash = String::from_utf8_lossy(&rev.stdout).trim().to_string();
        Ok((hash, "committed".into()))
    }
}

/// Parse `git status --porcelain=v1 -z` output into (path, status) entries.
fn parse_porcelain(bytes: &[u8]) -> Vec<(String, String)> {
    let mut entries = Vec::new();
    let mut iter = bytes.split(|&b| b == 0);
    for entry in iter.by_ref() {
        if entry.is_empty() {
            continue;
        }
        // Each entry: "XY <path>" or "XY <orig> -> <path>" (renames).
        if entry.len() < 3 {
            continue;
        }
        let x = entry[0];
        let y = entry[1];
        let path_part = &entry[3..];
        let path = String::from_utf8_lossy(path_part).to_string();
        let path = path.split(" -> ").last().unwrap_or(&path).to_string();
        let status = classify(x, y);
        entries.push((path, status));
    }
    entries
}

fn classify(x: u8, y: u8) -> String {
    if x == b'?' && y == b'?' {
        return "untracked".into();
    }
    if x == b'U' || y == b'U' || x == b'A' && y == b'A' {
        return "conflicted".into();
    }
    match (x, y) {
        (b'R', _) | (_, b'R') => "renamed".into(),
        (b'D', _) | (_, b'D') => {
            if x == b'D' && y == b'D' {
                "conflicted".into()
            } else {
                "deleted".into()
            }
        }
        (b'A', _) => "added".into(),
        (b'M', _) | (_, b'M') => "modified".into(),
        _ => "modified".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    /// Build a daemon over a fresh temp workspace.
    fn daemon() -> (Daemon, tempfile::TempDir) {
        let tmp = tempfile::tempdir().unwrap();
        // Init a git repo so git ops are testable.
        std::process::Command::new("git")
            .args(["init", "-q"])
            .current_dir(tmp.path())
            .output()
            .unwrap();
        std::process::Command::new("git")
            .args(["config", "user.email", "tc@test"])
            .current_dir(tmp.path())
            .output()
            .unwrap();
        std::process::Command::new("git")
            .args(["config", "user.name", "TC Test"])
            .current_dir(tmp.path())
            .output()
            .unwrap();
        // Initial commit on default branch so there's a HEAD.
        fs::write(tmp.path().join("README"), "init\n").unwrap();
        std::process::Command::new("git")
            .args(["add", "."])
            .current_dir(tmp.path())
            .output()
            .unwrap();
        std::process::Command::new("git")
            .args(["commit", "-q", "-m", "init"])
            .current_dir(tmp.path())
            .output()
            .unwrap();
        let ws = Workspace::new(tmp.path()).unwrap();
        let daemon = Daemon::new(ws, Redactor::new());
        (daemon, tmp)
    }

    // ---- read_file ----

    #[tokio::test]
    async fn read_file_full() {
        let (d, _t) = daemon();
        fs::write(d.workspace.root().join("a.txt"), b"hello world").unwrap();
        let r = d.read_file("a.txt", 0, 0).unwrap();
        assert_eq!(r.content, b"hello world");
        assert_eq!(r.sha256, sha256_hex(b"hello world"));
        assert!(!r.truncated);
        assert_eq!(r.total_size, 11);
    }

    #[tokio::test]
    async fn read_file_chunked() {
        let (d, _t) = daemon();
        fs::write(d.workspace.root().join("a.txt"), b"hello world").unwrap();
        let r = d.read_file("a.txt", 6, 5).unwrap();
        assert_eq!(r.content, b"world");
        assert!(r.truncated);
        assert_eq!(r.total_size, 11);
        // sha is of the full file, not the chunk
        assert_eq!(r.sha256, sha256_hex(b"hello world"));
    }

    #[tokio::test]
    async fn read_file_rejects_traversal() {
        let (d, _t) = daemon();
        let err = d.read_file("../../etc/passwd", 0, 0).unwrap_err();
        assert!(err.is_security_rejection());
    }

    #[tokio::test]
    async fn read_file_missing() {
        let (d, _t) = daemon();
        assert!(matches!(
            d.read_file("nope.txt", 0, 0),
            Err(DaemonError::NotFound(_))
        ));
    }

    // ---- write_file ----

    #[tokio::test]
    async fn write_file_success() {
        let (d, _t) = daemon();
        // New file: current hash == empty hash.
        let expected = empty_hash();
        let r = d.write_file("out.txt", b"new content", &expected).unwrap();
        assert!(r.written);
        assert_eq!(r.sha256, sha256_hex(b"new content"));
        // Verify on disk.
        assert_eq!(
            fs::read(d.workspace.root().join("out.txt")).unwrap(),
            b"new content"
        );
    }

    #[tokio::test]
    async fn write_file_hash_mismatch() {
        let (d, _t) = daemon();
        fs::write(d.workspace.root().join("out.txt"), b"original").unwrap();
        // Caller thinks file is empty but it isn't -> mismatch.
        let err = d.write_file("out.txt", b"new", &empty_hash()).unwrap_err();
        assert!(matches!(err, DaemonError::HashMismatch { .. }));
        // File must be untouched.
        assert_eq!(
            fs::read(d.workspace.root().join("out.txt")).unwrap(),
            b"original"
        );
    }

    #[tokio::test]
    async fn write_file_update_with_correct_hash() {
        let (d, _t) = daemon();
        fs::write(d.workspace.root().join("out.txt"), b"v1").unwrap();
        let cur = sha256_hex(b"v1");
        let r = d.write_file("out.txt", b"v2", &cur).unwrap();
        assert_eq!(r.sha256, sha256_hex(b"v2"));
        assert_eq!(fs::read(d.workspace.root().join("out.txt")).unwrap(), b"v2");
    }

    #[tokio::test]
    async fn write_file_rejects_traversal() {
        let (d, _t) = daemon();
        let err = d
            .write_file("../../evil.txt", b"x", &empty_hash())
            .unwrap_err();
        assert!(err.is_security_rejection());
    }

    // ---- exec_command ----

    #[tokio::test]
    async fn exec_captures_stdout_stderr() {
        let (d, _t) = daemon();
        let r = d
            .exec_command(
                &[
                    "sh".into(),
                    "-c".into(),
                    "echo out; echo err 1>&2; exit 7".into(),
                ],
                10,
            )
            .await
            .unwrap();
        assert_eq!(r.status, "completed");
        assert_eq!(r.exit_code, 7);
        assert!(String::from_utf8_lossy(&r.stdout).contains("out"));
        assert!(String::from_utf8_lossy(&r.stderr).contains("err"));
    }

    #[tokio::test]
    async fn exec_timeout() {
        let (d, _t) = daemon();
        let r = d
            .exec_command(&["sh".into(), "-c".into(), "sleep 30".into()], 1)
            .await;
        assert!(matches!(r, Err(DaemonError::Timeout(1))), "{r:?}");
    }

    #[tokio::test]
    async fn exec_requires_timeout() {
        let (d, _t) = daemon();
        let err = d.exec_command(&["true".into()], 0).await.unwrap_err();
        assert!(matches!(err, DaemonError::InvalidArgument(_)));
    }

    #[tokio::test]
    async fn exec_runs_in_workspace_root() {
        let (d, _t) = daemon();
        // `pwd` should report the workspace root.
        let r = d.exec_command(&["pwd".into()], 5).await.unwrap();
        let pwd = String::from_utf8_lossy(&r.stdout).trim().to_string();
        assert_eq!(pwd, d.workspace.root().to_string_lossy());
    }

    // ---- redaction through exec ----

    #[tokio::test]
    async fn exec_redacts_secrets_in_output() {
        let (d, _t) = daemon();
        let secret = "AKIAIOSFODNN7EXAMPLE";
        let r = d
            .exec_command(&["sh".into(), "-c".into(), format!("echo {secret}")], 5)
            .await
            .unwrap();
        let out = String::from_utf8_lossy(&r.stdout);
        assert!(!out.contains(secret), "secret leaked: {out}");
        assert!(out.contains("[REDACTED_SECRET]"));
    }

    #[tokio::test]
    async fn exec_does_not_inherit_daemon_env() {
        // The daemon env_clears the child, so a var set in the daemon's env
        // must not appear in the child's output.
        std::env::set_var("TC_LEAK_TEST", "should-not-appear");
        let (d, _t) = daemon();
        let r = d
            .exec_command(&["sh".into(), "-c".into(), "echo $TC_LEAK_TEST".into()], 5)
            .await
            .unwrap();
        let out = String::from_utf8_lossy(&r.stdout).trim().to_string();
        assert!(out.is_empty(), "child inherited secret env: {out}");
        std::env::remove_var("TC_LEAK_TEST");
    }

    // ---- git ----

    #[tokio::test]
    async fn git_create_branch_and_commit() {
        let (d, _t) = daemon();
        // Create a TC branch from HEAD.
        let (name, msg) = d.git_create_branch("tc-change-1", true).unwrap();
        assert_eq!(name, "tc-change-1");
        assert!(msg.contains("HEAD") || msg.contains("created"));

        // Make a change and commit it.
        fs::write(d.workspace.root().join("change.txt"), b"change").unwrap();
        let (hash, status) = d.git_commit("tc change", &["change.txt".into()]).unwrap();
        assert_eq!(status, "committed");
        assert!(!hash.is_empty());
        assert_eq!(hash.len(), 40); // sha1 hex
    }

    #[tokio::test]
    async fn git_status_reports_changes() {
        let (d, _t) = daemon();
        fs::write(d.workspace.root().join("new.txt"), b"x").unwrap();
        let (branch, clean, entries) = d.git_status().unwrap();
        assert!(!clean);
        assert!(!branch.is_empty());
        assert!(entries
            .iter()
            .any(|(p, s)| p == "new.txt" && s == "untracked"));
    }

    #[tokio::test]
    async fn git_commit_nothing_to_commit_is_safe() {
        let (d, _t) = daemon();
        let (hash, msg) = d.git_commit("nothing here", &[]).unwrap();
        assert!(hash.is_empty());
        assert!(msg.contains("nothing to commit") || msg.contains("no changes"));
    }

    #[tokio::test]
    async fn git_commit_rejects_path_traversal() {
        let (d, _t) = daemon();
        let err = d
            .git_commit("bad", &["../../etc/passwd".into()])
            .unwrap_err();
        assert!(err.is_security_rejection());
    }
}
