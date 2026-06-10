#!/usr/bin/env bash
# 一键安装 burntoken：装依赖 + 加 PATH + alias + 准备 .env
#
# 此脚本位于项目根目录（与 bin/、.env.example、Makefile 同级）。
# SCRIPT_DIR 始终等于脚本所在目录，因此可以从任何位置调用。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
ENV_FILE="$SCRIPT_DIR/.env"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  burntoken 安装脚本（hbscloud Token 燃烧器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SCRIPT_DIR = $SCRIPT_DIR"
echo

# 1. 装 httpx
echo "▶ 步骤 1/4：检查 httpx 依赖"
if python3 -c "import httpx" >/dev/null 2>&1; then
  echo "  ✓ httpx 已安装"
else
  echo "  正在安装 httpx ..."
  pip3 install --user --quiet httpx 2>&1 | tail -3 || {
    echo "  pip 安装失败，尝试 uv："
    uv pip install --system httpx 2>&1 | tail -3
  }
fi
echo

# 2. 检测 shell
echo "▶ 步骤 2/4：检测 shell 配置"
SHELL_RC=""
case "${SHELL:-/bin/zsh}" in
  */zsh)  SHELL_RC="$HOME/.zshrc" ;;
  */bash) SHELL_RC="$HOME/.bashrc" ;;
  */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
  *)      SHELL_RC="$HOME/.zshrc" ;;
esac
echo "  shell = $SHELL"
echo "  rc    = $SHELL_RC"
echo

# 3. 写 PATH + alias
echo "▶ 步骤 3/4：写入 PATH 和 alias"
MARK="# >>> burntoken >>>"
END_MARK="# <<< burntoken <<<"
if [ -f "$SHELL_RC" ] && grep -q "$MARK" "$SHELL_RC"; then
  echo "  ✓ $SHELL_RC 已包含 burntoken 配置，跳过"
else
  {
    echo ""
    echo "$MARK"
    echo "export PATH=\"\$PATH:$BIN_DIR\""
    echo "alias burntoken='$BIN_DIR/burntoken'"
    echo "$END_MARK"
  } >> "$SHELL_RC"
  echo "  ✓ 已追加到 $SHELL_RC"
fi
echo

# 4. .env
echo "▶ 步骤 4/4：配置 .env"
if [ -f "$ENV_EXAMPLE" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "  ✓ 已生成 .env（权限 600）"
    echo "  ⚠️  请编辑填入 HBS_API_KEY："
    echo "     ${EDITOR:-nano} $ENV_FILE"
  else
    echo "  ✓ .env 已存在"
  fi
else
  echo "  ✗ 找不到 $ENV_EXAMPLE，跳过 .env 生成"
fi
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ 安装完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "立即生效："
echo "  source $SHELL_RC"
echo
echo "使用："
echo "  burntoken -p \"用一句话说 hello\"            # 单条"
echo "  burntoken -p \"写首诗\" --stream              # 流式"
echo "  burntoken burn --preset code -n 20 -P 4     # 批量并发烧"
echo "  burntoken --repl                              # 交互 REPL"
echo "  burntoken --models                            # 列出模型"
echo
echo "⚠️  请确认 HBS_API_KEY 已正确填入 .env"
