#!/usr/bin/env bash
# 禁止 Case 层 test 模块互 import（support 除外）。
# 匹配：from tests.<domain>.test_...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATTERN='from tests\.(catalog|user|infra|health|ops)\.test_'

if rg -n --glob '*.py' "${PATTERN}" "${ROOT}/tests"; then
  echo "error: 禁止 test 模块互 import（请改用 tests.support.*）" >&2
  echo "pattern: ${PATTERN}" >&2
  exit 1
fi

echo "ok: 无 test 模块互 import"
