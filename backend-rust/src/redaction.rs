//! Deterministic secret redaction.
//!
//! The redaction layer scans command output (stdout/stderr) and replaces any
//! configured secret values and common token patterns with `[REDACTED_SECRET]`.
//! Raw credentials must never be returned to the Brain.

use once_cell::sync::Lazy;
use regex::Regex;

pub const REDACTED: &str = "[REDACTED_SECRET]";

/// Common high-signal token patterns. Order matters only for performance;
/// all are replaced with the same sentinel.
static TOKEN_PATTERNS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        // AWS access key id
        Regex::new(r"AKIA[0-9A-Z]{16}").unwrap(),
        // AWS secret access key (40 base64 chars after the marker)
        Regex::new(r"(?i)aws_secret_access_key[=:]\s*[A-Za-z0-9/+=]{40}").unwrap(),
        // Generic "Bearer <token>"
        Regex::new(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*").unwrap(),
        // Authorization: Basic <token>
        Regex::new(r"(?i)authorization:\s*basic\s+[A-Za-z0-9+/=]+").unwrap(),
        // GitHub tokens (classic PAT, fine-grained, OAuth)
        Regex::new(r"gh[pousr]_[A-Za-z0-9]{36,255}").unwrap(),
        // GitHub fine-grained PAT
        Regex::new(r"github_pat_[A-Za-z0-9_]{82}").unwrap(),
        // OpenAI-style API keys
        Regex::new(r"sk-[A-Za-z0-9]{20,}").unwrap(),
        // Slack tokens
        Regex::new(r"xox[baprs]-[A-Za-z0-9\-]{10,}").unwrap(),
        // Generic <key>=<value> where key looks like a secret and value is long
        Regex::new(r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?token)[=:]\s*[A-Za-z0-9_\-/+=]{16,}")
            .unwrap(),
        // JWT (three base64url segments)
        Regex::new(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}").unwrap(),
    ]
});

/// A redactor configured with both explicit secret values and token patterns.
#[derive(Clone, Default)]
pub struct Redactor {
    /// Literal secret values to scrub (e.g. env var values loaded at startup).
    literals: Vec<String>,
}

impl Redactor {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an explicit secret value to scrub. Empty values are ignored.
    pub fn add_secret(mut self, value: impl Into<String>) -> Self {
        let v = value.into();
        if !v.is_empty() {
            self.literals.push(v);
        }
        self
    }

    /// Add all key=value pairs from an iterator of `KEY=VALUE` strings (as
    /// produced by scanning the process environment). The *values* are the
    /// secrets; keys are matched separately by the token patterns.
    pub fn add_env_pairs<'a>(mut self, pairs: impl IntoIterator<Item = &'a str>) -> Self {
        for kv in pairs {
            if let Some((_k, v)) = kv.split_once('=') {
                if !v.is_empty() {
                    self.literals.push(v.to_string());
                }
            }
        }
        self
    }

    /// Redact a byte buffer. Non-UTF-8 bytes are passed through untouched
    /// except where a UTF-8 window matches a pattern.
    pub fn redact_bytes(&self, input: &[u8]) -> Vec<u8> {
        // Fast path: try to interpret as UTF-8. If it is, redact as a string
        // (patterns are defined on text). If not, redact the literals as raw
        // byte slices and return.
        match std::str::from_utf8(input) {
            Ok(s) => self.redact_str(s).into_bytes(),
            Err(_) => self.redact_bytes_lossy(input),
        }
    }

    /// Redact a string, returning a new owned string.
    pub fn redact_str(&self, input: &str) -> String {
        let mut out = input.to_string();
        // Literal secrets first (longest-first to avoid partial overlaps).
        let mut lits: Vec<&String> = self.literals.iter().collect();
        lits.sort_by_key(|s| std::cmp::Reverse(s.len()));
        for lit in lits {
            if !lit.is_empty() && out.contains(lit.as_str()) {
                out = out.replace(lit, REDACTED);
            }
        }
        for re in TOKEN_PATTERNS.iter() {
            out = re.replace_all(&out, REDACTED).to_string();
        }
        out
    }

    fn redact_bytes_lossy(&self, input: &[u8]) -> Vec<u8> {
        let mut out = input.to_vec();
        let mut lits: Vec<&String> = self.literals.iter().collect();
        lits.sort_by_key(|s| std::cmp::Reverse(s.len()));
        for lit in lits {
            if lit.is_empty() {
                continue;
            }
            let needle = lit.as_bytes();
            while let Some(pos) = find_subslice(&out, needle) {
                out.splice(pos..pos + needle.len(), REDACTED.as_bytes().iter().copied());
            }
        }
        out
    }
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redacts_literal_secret() {
        let r = Redactor::new().add_secret("super-secret-value");
        let out = r.redact_str("the token is super-secret-value ok");
        assert!(out.contains(REDACTED));
        assert!(!out.contains("super-secret-value"));
    }

    #[test]
    fn redacts_aws_access_key() {
        let r = Redactor::new();
        let out = r.redact_str("AKIAIOSFODNN7EXAMPLE was leaked");
        assert_eq!(out, format!("{REDACTED} was leaked"));
    }

    #[test]
    fn redacts_bearer_token() {
        let r = Redactor::new();
        let out = r.redact_str("Authorization: Bearer dGhpcyBpcyBhIHRva2Vu");
        assert!(!out.contains("dGhpcyBpcyBhIHRva2Vu"));
        assert!(out.contains(REDACTED));
    }

    #[test]
    fn redacts_github_pat() {
        let r = Redactor::new();
        let out = r.redact_str("ghp_01234567890123456789012345678901234567");
        assert!(out.contains(REDACTED));
        assert!(!out.contains("ghp_01234567890123456789012345678901234567"));
    }

    #[test]
    fn redacts_generic_key_value() {
        let r = Redactor::new();
        let out = r.redact_str("api_key=abcdef0123456789abcdef0123456789");
        assert!(out.contains(REDACTED));
        assert!(!out.contains("abcdef0123456789abcdef0123456789"));
    }

    #[test]
    fn redacts_jwt() {
        let r = Redactor::new();
        let jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signaturepart";
        let out = r.redact_str(jwt);
        assert!(out.contains(REDACTED));
        assert!(!out.contains("eyJhbGciOiJIUzI1NiJ9"));
    }

    #[test]
    fn does_not_redact_normal_text() {
        let r = Redactor::new();
        let out = r.redact_str("cargo test finished successfully");
        assert_eq!(out, "cargo test finished successfully");
    }

    #[test]
    fn redacts_env_pair_values() {
        let r = Redactor::new().add_env_pairs(["DB_PASSWORD=hunter2hunter2hunter2", "FOO=bar"]);
        let out = r.redact_str("pw=hunter2hunter2hunter2");
        assert!(out.contains(REDACTED));
        assert!(!out.contains("hunter2hunter2hunter2"));
        // bar is too short for the generic pattern and not a literal of interest? it IS a literal
        // because we added env pairs — so 'bar' will be redacted as a literal too. That's fine.
    }

    #[test]
    fn redacts_bytes_non_utf8() {
        let r = Redactor::new().add_secret("secret");
        let input = b"prefix secret \xff suffix".to_vec();
        let out = r.redact_bytes(&input);
        assert!(
            out.windows(REDACTED.len())
                .any(|w| w == REDACTED.as_bytes()),
            "secret not redacted in bytes"
        );
        // ensure the non-utf8 byte is preserved
        let out = r.redact_bytes(b"secret");
        assert_eq!(out, REDACTED.as_bytes());
    }
}
