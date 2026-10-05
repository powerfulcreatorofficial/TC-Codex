"""Validate every JSON file under the repo root parses cleanly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Skip dependency / build output directories that are not our source.
SKIP_DIRS = {"node_modules", ".next", "target", ".git", ".venv"}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def main() -> int:
    files = [p for p in sorted(ROOT.rglob("*.json")) if not should_skip(p)]
    if not files:
        print("No JSON files found", file=sys.stderr)
        return 1
    failures: list[str] = []
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                json.load(fh)
            print(f"OK   {path.relative_to(ROOT)}")
        except Exception as exc:  # noqa: BLE001 - report any parse failure
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            print(f"FAIL {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
    if failures:
        return 1
    print(f"\nAll {len(files)} JSON file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
