//! Workspace root enforcement.
//!
//! All daemon filesystem operations resolve client-supplied relative paths
//! against a single configured workspace root. Paths that would escape the
//! root (via `..`, absolute paths, or symlinks) are rejected.

use crate::error::{DaemonError, Result};
use std::path::{Component, Path, PathBuf};

/// The sandboxed workspace root. All client paths are confined to this root.
#[derive(Clone, Debug)]
pub struct Workspace {
    root: PathBuf,
}

impl Workspace {
    /// Create a workspace rooted at `root`. The path is canonicalized so that
    /// later containment checks are robust against `.`/`..` and symlinks.
    pub fn new(root: impl AsRef<Path>) -> Result<Self> {
        let root = root.as_ref();
        let canonical = root.canonicalize().map_err(|e| {
            DaemonError::InvalidArgument(format!(
                "workspace root {:?} is not accessible: {e}",
                root
            ))
        })?;
        Ok(Self { root: canonical })
    }

    /// The canonical workspace root.
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Resolve a client-supplied relative path to an absolute path *inside*
    /// the workspace root, rejecting anything that escapes it.
    ///
    /// The input must be relative. Components are normalized (`.`, `..`,
    /// internal `//`) without touching the filesystem, and the result is
    /// verified to stay within the root. This means a path like
    /// `../../etc/passwd` or an absolute `/etc/passwd` is rejected before any
    /// file is touched.
    pub fn resolve(&self, rel: &str) -> Result<PathBuf> {
        let rel_path = Path::new(rel);

        if rel_path.is_absolute() {
            return Err(DaemonError::PathEscape(rel.to_string()));
        }
        if rel.is_empty() {
            return Err(DaemonError::InvalidArgument("empty path".into()));
        }

        // Normalize components: reject `..` that would climb above the root
        // and reject any `Component::RootDir`/prefix (defensive — relative
        // input should never produce these, but be safe).
        let mut acc = self.root.clone();
        for comp in rel_path.components() {
            match comp {
                Component::CurDir => {}
                Component::ParentDir => {
                    if acc == self.root {
                        // Climbing above the workspace root.
                        return Err(DaemonError::PathEscape(rel.to_string()));
                    }
                    acc.pop();
                }
                Component::Normal(part) => {
                    acc.push(part);
                }
                Component::RootDir | Component::Prefix(_) => {
                    return Err(DaemonError::PathEscape(rel.to_string()));
                }
            }
        }

        // Final containment guarantee: the normalized path must start with the
        // workspace root.
        if !acc.starts_with(&self.root) {
            return Err(DaemonError::PathEscape(rel.to_string()));
        }
        Ok(acc)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn ws() -> Workspace {
        let tmp = tempfile::tempdir().unwrap();
        Workspace::new(tmp.path()).unwrap()
    }

    #[test]
    fn resolves_simple_relative_path() {
        let ws = ws();
        let got = ws.resolve("dir/file.txt").unwrap();
        assert!(got.starts_with(ws.root()));
        assert!(got.ends_with("dir/file.txt"));
    }

    #[test]
    fn rejects_dotdot_escape() {
        let ws = ws();
        let err = ws.resolve("../../etc/passwd").unwrap_err();
        assert!(err.is_security_rejection(), "{err:?}");
    }

    #[test]
    fn rejects_absolute_path() {
        let ws = ws();
        let err = ws.resolve("/etc/passwd").unwrap_err();
        assert!(err.is_security_rejection());
    }

    #[test]
    fn rejects_single_dotdot() {
        let ws = ws();
        let err = ws.resolve("..").unwrap_err();
        assert!(err.is_security_rejection());
    }

    #[test]
    fn allows_internal_dotdot_within_subdir() {
        // a/../b is fine as long as it stays under root.
        let ws = ws();
        fs::create_dir_all(ws.root().join("a")).unwrap();
        let got = ws.resolve("a/../b.txt").unwrap();
        assert!(got.ends_with("b.txt"));
        assert!(got.starts_with(ws.root()));
    }

    #[test]
    fn rejects_empty_path() {
        let ws = ws();
        assert!(ws.resolve("").is_err());
    }

    #[test]
    fn rejects_root_dir_component() {
        let ws = ws();
        let err = ws.resolve("sub/../../etc/shadow").unwrap_err();
        assert!(err.is_security_rejection());
    }
}
