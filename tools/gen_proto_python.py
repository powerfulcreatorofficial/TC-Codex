#!/usr/bin/env python3
"""Regenerate the Python gRPC stubs for the Workspace Daemon.

Run from anywhere; regenerates the committed stubs in
tc-orchestrator/src/tc_orchestrator/proto_gen/ from the protos copied there.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent.parent / "tc-orchestrator" / "src" / "tc_orchestrator" / "proto_gen"


def main() -> int:
    if not GEN_DIR.exists():
        print(f"proto_gen dir not found: {GEN_DIR}", file=sys.stderr)
        return 1
    protos = ["daemon.proto", "health.proto"]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I.",
            "--python_out=.",
            "--grpc_python_out=.",
            "--pyi_out=.",
            *protos,
        ],
        cwd=GEN_DIR,
        check=True,
    )
    # Patch top-level `import <name>_pb2` to relative imports inside the package.
    for grpc_file in GEN_DIR.glob("*_pb2_grpc.py"):
        text = grpc_file.read_text()
        text = re.sub(r"^import (\w+_pb2) as (\w+)", r"from . import \1 as \2", text, flags=re.MULTILINE)
        grpc_file.write_text(text)
    print(f"Regenerated stubs in {GEN_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
