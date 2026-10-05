#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python -m compileall -q tc-orchestrator/src/tc_orchestrator
PYTHONPATH="$ROOT/tc-orchestrator/src" python -m pytest -q tc-orchestrator/tests/test_delegation_master.py
python - <<'PY'
from tc_orchestrator.master import TCMaster
m = TCMaster.create(root='.tc/check-jobs')
print('master-capabilities', len(m.capabilities()))
print('master-ready')
PY
