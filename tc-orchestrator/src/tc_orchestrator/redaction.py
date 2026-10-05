"""Orchestrator-side output redaction (defense in depth).

The Workspace Daemon already redacts its own output; this layer is a second
line of defense that scrubs anything that slipped through (or that was
produced by the orchestrator itself) before it ever reaches the Brain.

Detected secrets are replaced with ``[REDACTED_SECRET]``. Raw credentials are
never logged.
"""

from __future__ import annotations

import os
import re

REDACTED = "[REDACTED_SECRET]"

# Common high-signal token patterns. Order is irrelevant; all map to the same
# sentinel. Patterns are compiled once.
_TOKEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{8,}"),  # OpenRouter
    re.compile(r"sk-[A-Za-z0-9]{8,}"),  # OpenAI-style
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),  # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),  # GitHub fine-grained PAT
    re.compile(r"\d{6,10}:AA[A-Za-z0-9_\-]{8,}"),  # Telegram bot tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),  # Bearer tokens
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),  # private-key blocks
    re.compile(
        r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?token)[=:]\s*"
        r"[A-Za-z0-9_\-/+=]{8,}"
    ),  # generic key=value secrets
]


def _env_secret_values() -> list[str]:
    """Collect secret *values* from env vars whose name looks like a secret.

    Only the values are collected (never the keys); they are used to scrub
    literal occurrences. Empty values are ignored.
    """
    secret_name_markers = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PASSWD",
        "API_KEY",
        "APIKEY",
        "PRIVATE_KEY",
        "ACCESS_KEY",
        "CREDENTIAL",
    )
    out: list[str] = []
    for name, value in os.environ.items():
        if not value:
            continue
        upper = name.upper()
        if any(m in upper for m in secret_name_markers):
            out.append(value)
    return out


class Redactor:
    """Deterministic redactor over configured literal secrets + token regexes."""

    def __init__(self, extra_secrets: list[str] | None = None) -> None:
        literals = [s for s in (extra_secrets or []) if s]
        # Deduplicate; longest-first to avoid partial overlaps.
        literals = sorted(set(literals), key=len, reverse=True)
        self._literals = literals

    @classmethod
    def from_env(cls, extra_secrets: list[str] | None = None) -> Redactor:
        return cls((extra_secrets or []) + _env_secret_values())

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        for lit in self._literals:
            if lit and lit in out:
                out = out.replace(lit, REDACTED)
        for pat in _TOKEN_PATTERNS:
            out = pat.sub(REDACTED, out)
        return out
