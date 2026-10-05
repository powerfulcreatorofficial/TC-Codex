#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../TC-ENGINEERING-AI-MASTER.zip}"
rm -f "$OUT"
cd "$ROOT/.."
zip -qr "$OUT" "$(basename "$ROOT")" -x '*/.git/*' '*/node_modules/*' '*/.next/*' '*/target/*' '*/.tc/*' '*/__pycache__/*' '*/.DS_Store'
python - <<PY
from zipfile import ZipFile
p=r'''$OUT'''
with ZipFile(p) as z:
    bad=z.testzip()
    print('zip-testzip:', bad)
    print('entries:', len(z.infolist()))
PY
echo "$OUT"
