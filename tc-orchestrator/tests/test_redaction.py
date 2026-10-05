"""TEST F — Secret redaction."""

from __future__ import annotations

import pytest

from tc_orchestrator.redaction import REDACTED, Redactor


@pytest.mark.parametrize(
    "text,has_secret",
    [
        ("key=sk-or-v1-TESTSECRET123 leak", True),
        ("token ghp_TESTSECRET123abcabcabcabcabcabcabcabcabcabc", True),
        ("telegram 123456789:AA_TEST_TELEGRAM_TOKEN_extra", True),
        ("aws AKIAIOSFODNN7EXAMPLE here", True),
        ("Authorization: Bearer dGhpcyBpcyBhIHRva2Vu", True),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signaturepart", True),
        ("normal cargo test output", False),
    ],
)
def test_common_patterns_redacted(text, has_secret, redactor_secrets):
    r = Redactor()
    out = r.redact(text)
    if has_secret:
        assert "[REDACTED_SECRET]" in out
    # A "secret"-flagged value should never survive redaction.
    for v in redactor_secrets.values():
        assert v not in out


def test_configured_env_secrets_redacted():
    import os

    os.environ["TC_TEST_SECRET"] = "supersecretvalue1234567890"
    try:
        r = Redactor.from_env()
        out = r.redact("the value is supersecretvalue1234567890")
        assert "supersecretvalue1234567890" not in out
        assert "[REDACTED_SECRET]" in out
    finally:
        del os.environ["TC_TEST_SECRET"]


def test_extra_secrets_redacted(redactor_secrets):
    r = Redactor(extra_secrets=list(redactor_secrets.values()))
    for v in redactor_secrets.values():
        out = r.redact(f"leak: {v}")
        assert v not in out
        assert REDACTED in out


def test_empty_string_passthrough():
    assert Redactor().redact("") == ""
