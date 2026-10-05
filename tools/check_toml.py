"""Validate every TOML file under the repo root parses without error."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = sorted(ROOT.rglob("*.toml"))
    if not files:
        print("No TOML files found", file=sys.stderr)
        return 1
    failures: list[str] = []
    for path in files:
        try:
            with path.open("rb") as fh:
                tomllib.load(fh)
            print(f"OK   {path.relative_to(ROOT)}")
        except Exception as exc:  # noqa: BLE001 - report any parse failure
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            print(f"FAIL {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
    if failures:
        return 1
    print(f"\nAll {len(files)} TOML file(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
