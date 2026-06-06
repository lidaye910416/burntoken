#!/usr/bin/env bash
# scripts/smoke-test.sh
# 手动 smoke test: 用 fixture 跑一轮

set -euo pipefail

cd "$(dirname "$0")/.."

# 用 env 提供假 key
export HBS_API_KEY="sk-test-fake"
export TRIBUNAL_CALIB_DIR="/tmp/tribunal-calib-test"
export TRIBUNAL_NONINTERACTIVE=1

echo "=== Smoke test: 1 round on fixture ==="
node .claude/workflows/burn-review-tribunal.js \
  --target .claude/skills/burn-review-tribunal/tests/fixtures/buggy-sample.py \
  --max-rounds 1 \
  --token-budget 10 \
  --no-interactive \
  --lens security

echo "=== Expected: 至少 1 个 finding (shell injection in process_user_path) ==="
echo "=== Done ==="
