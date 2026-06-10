#!/usr/bin/env bash
# examples/00-version.sh
# Self-check: 确认 __version__ 暴露 + CLI --version 输出匹配 semver 模式
#
# 目的: 给新用户提供一个"装好之后怎么验"的最小例子。
# 任何时刻对版本号实现有疑问，跑一下这个脚本即可。
#
# 注意: 本脚本只用 ASCII 括号, 不使用全角 （）.
# 原因: macOS 自带的 bash 3.2 在 set -u 下, $VAR 紧邻全角 ) 时会
# 误把后半个 UTF-8 字节当成变量名的一部分, 报 unbound variable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 用项目本地的 bin/, 保证测试的就是当前 checkout 而不是 PATH 上的旧版本
BIN="$PROJECT_DIR/bin/burntoken"

# Semver 正则: MAJOR.MINOR.PATCH, 可选 -prerelease / +build
SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$'

echo "[1/3] python -c 'import burntoken; print(burntoken.__version__)'"
PY_VERSION="$(cd "$PROJECT_DIR" && python3 -c 'import burntoken; print(burntoken.__version__)')"
echo "  输出: $PY_VERSION"
if ! [[ "$PY_VERSION" =~ $SEMVER_RE ]]; then
  echo "  [FAIL] $PY_VERSION 不是合法 semver" >&2
  exit 1
fi
echo "  [OK] 匹配 semver"

echo
echo "[2/3] burntoken --version"
CLI_OUTPUT="$("$BIN" --version)"
echo "  输出: $CLI_OUTPUT"
CLI_PREFIX="burntoken "
if [[ "$CLI_OUTPUT" != "$CLI_PREFIX"* ]]; then
  echo "  [FAIL] $CLI_OUTPUT 不是以 $CLI_PREFIX 开头" >&2
  exit 1
fi
CLI_VERSION="${CLI_OUTPUT#$CLI_PREFIX}"
if ! [[ "$CLI_VERSION" =~ $SEMVER_RE ]]; then
  echo "  [FAIL] $CLI_VERSION 不是合法 semver" >&2
  exit 1
fi
echo "  [OK] CLI 报出版本: $CLI_VERSION"

echo
echo "[3/3] python 和 CLI 版本号一致"
if [[ "$PY_VERSION" != "$CLI_VERSION" ]]; then
  echo "  [FAIL] python=$PY_VERSION  cli=$CLI_VERSION" >&2
  exit 1
fi
echo "  [OK] python 和 CLI 一致"

echo
echo "[PASS] examples/00-version.sh 全部自检通过 (burntoken $PY_VERSION)"
