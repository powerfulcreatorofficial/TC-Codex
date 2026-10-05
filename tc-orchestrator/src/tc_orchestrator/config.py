"""Environment-driven configuration for the TC Orchestrator.

All configuration is read from environment variables. No API keys are
hard-coded; secrets are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Primary Brain (OpenAI-compatible Chat Completions).
    brain_base_url: str | None
    brain_api_key: str | None
    brain_model: str

    # Workspace Daemon gRPC endpoint (default matches the daemon default).
    daemon_addr: str

    # Agent loop bound.
    max_agent_steps: int

    # HTTP server bind address.
    host: str
    port: int

    # PostgreSQL persistence (Step 4). None => in-memory store.
    database_url: str | None
    # Approval workflow (Step 4). When True, L1/L2 tools pause for approval.
    require_approval: bool
    # Seconds before a pending approval expires.
    approval_expiry_seconds: int
    # Maximum bounded automatic repair attempts per task.
    max_repair_attempts: int = 3

    # Multi-brain routing / cost control. Defaults preserve existing behavior:
    # higher brain is disabled until explicitly configured.
    higher_brain_base_url: str | None = "https://api.openai.com/v1"
    higher_brain_api_key: str | None = None
    higher_brain_model: str = "gpt-6-astra"
    higher_brain_protocol: str = "responses"
    higher_brain_enabled: bool = False
    higher_brain_max_usd: float = 0.50
    higher_brain_max_calls: int = 3
    primary_input_usd_per_mtok: float = 0.15
    primary_output_usd_per_mtok: float = 2.0
    higher_input_usd_per_mtok: float = 10.0
    higher_output_usd_per_mtok: float = 50.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            brain_base_url=_env("PRIMARY_BRAIN_BASE_URL", _env("BRAIN_BASE_URL", "https://openrouter.ai/api/v1")),
            brain_api_key=_env("PRIMARY_BRAIN_API_KEY", _env("BRAIN_API_KEY")),
            brain_model=_env("PRIMARY_BRAIN_MODEL", _env("BRAIN_MODEL", "qwen/qwen3.8-27b")),
            higher_brain_base_url=_env("HIGHER_BRAIN_BASE_URL", "https://api.openai.com/v1"),
            higher_brain_api_key=_env("HIGHER_BRAIN_API_KEY"),
            higher_brain_model=_env("HIGHER_BRAIN_MODEL", "gpt-6-astra"),
            higher_brain_protocol=_env("HIGHER_BRAIN_PROTOCOL", "responses"),
            higher_brain_enabled=_env_bool("HIGHER_BRAIN_ENABLED", False),
            higher_brain_max_usd=_env_float("HIGHER_BRAIN_MAX_USD", 0.50),
            higher_brain_max_calls=_env_int("HIGHER_BRAIN_MAX_CALLS", 3),
            primary_input_usd_per_mtok=_env_float("PRIMARY_INPUT_USD_PER_MTOK", 0.15),
            primary_output_usd_per_mtok=_env_float("PRIMARY_OUTPUT_USD_PER_MTOK", 2.0),
            higher_input_usd_per_mtok=_env_float("HIGHER_INPUT_USD_PER_MTOK", 10.0),
            higher_output_usd_per_mtok=_env_float("HIGHER_OUTPUT_USD_PER_MTOK", 50.0),
            daemon_addr=_env("TC_DAEMON_ADDR", "127.0.0.1:50051"),
            max_agent_steps=_env_int("MAX_AGENT_STEPS", 20),
            max_repair_attempts=_env_int("MAX_REPAIR_ATTEMPTS", 3),
            host=_env("TC_ORCH_HOST", "127.0.0.1"),
            port=_env_int("TC_ORCH_PORT", 8080),
            database_url=_env("DATABASE_URL"),
            require_approval=_env_bool("TC_REQUIRE_APPROVAL", True),
            approval_expiry_seconds=_env_int("TC_APPROVAL_EXPIRY_SECONDS", 300),
        )


def load_settings() -> Settings:
    return Settings.from_env()
