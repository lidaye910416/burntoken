#!/usr/bin/env bash
# =============================================================
#  03-batch-burn.sh
#  演示：批量烧 token（这是 burntoken 的主菜）
#  5 个内置 preset：chat / math / code / essay / longctx
#
#  使用：
#    ./examples/03-batch-burn.sh        # 真的会发请求，先把 .env 配好
#    ./examples/03-batch-burn.sh demo   # 仅打印命令，不执行
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
[ -f .env ] && { set -a; source .env; set +a; }

MODE="${1:-run}"

run() {
  echo
  echo "============================================================"
  echo "  $1"
  echo "============================================================"
  shift
  if [ "$MODE" = "demo" ]; then
    printf "  \$ %s\n" "$*"
  else
    eval "$@"
  fi
}

# 1) 短答：20 次，4 并发
run "1) chat 短答 · 20 次 / 4 并发" \
  ./bin/burntoken burn --preset chat -n 20 -P 4
# 预期输出：
# burntoken/chat |█████████████████████░░░| 20/20 100.0% elapsed= 6.4s eta= 0.0s
# ════════════════════════════════════════════════════════════
#   burntoken 完成 · model=hbscloud-glm
# ════════════════════════════════════════════════════════════
#   请求             20/20  (failed=0)
#   prompt tok     1,824
#   completion     1,206
#   total tok      3,030
#   耗时             6.4s
#   avg latency     932ms
#   吞吐             473.4 tok/s  ·  3.1 req/s
#   成本             ¥0.000
# ════════════════════════════════════════════════════════════

# 2) 代码：5 次，2 并发
run "2) code 生成 · 5 次 / 2 并发" \
  ./bin/burntoken burn --preset code -n 5 -P 2
# 预期：total ~4-6k tokens，每条 ~1-2 秒

# 3) 长文：3 次，单并发（避免超 rate-limit）
run "3) essay 长文 · 3 次 / 1 并发 / 2048 token" \
  ./bin/burntoken burn --preset essay -n 3 -P 1
# 预期：每条 ~2k completion，总 ~6-8k token

# 4) 长上下文：8 轮历史 × 10 次
run "4) longctx 长上下文 · 10 次 / 2 并发 / 8 轮历史" \
  ./bin/burntoken burn --preset longctx --multi-turn 8 -n 10 -P 2
# 预期：prompt ~3-4k / 条，completion ~200 / 条
# longctx 的特点是 prompt 大、completion 小（"总结以上对话"），
# 适合测"大输入成本"和"大 context 推理能力"。

# 5) 熔断：总 token ≤ 5000 自动停
run "5) 熔断 · 烧到 5000 token 自动停" \
  ./bin/burntoken burn --preset code -n 100 -P 4 --max-tokens 5000
# 预期中途触发熔断：
# burntoken/code |██████████████░░░░░░░░░| 6/100  6.0% ...
# ⚠ 触发熔断：tokens 5,021 ≥ 5,000
# （继续把已经在飞的请求跑完，然后打印汇总）

# 6) 熔断：总成本 ≤ ¥0.10 自动停
run "6) 熔断 · 成本超过 ¥0.10 自动停" \
  HBS_PRICE_PROMPT=0.001 HBS_PRICE_COMPLETION=0.002 \
    ./bin/burntoken burn --preset essay -n 50 -P 2 --max-cost 0.10
# 预期：HBS_PRICE_PROMPT/COMPLETION 是每 1k token 的价格（CNY/USD 自定），
# tracker 累计 cost，超阈值即停。

# 7) 落 jsonl：每条结果追加
run "7) 落 jsonl · 8 次 code" \
  ./bin/burntoken burn --preset code -n 8 -P 2 \
    --save logs/batch-burn.jsonl
# 预期：logs/batch-burn.jsonl 多 8 行，每行形如：
# {"type":"burn","idx":0,"model":"hbscloud-glm","preset":"code",
#  "text":"def binary_search...","usage":{"prompt_tokens":18,...},
#  "latency_ms":921}

# 8) 固定 seed：可复现
run "8) --seed 42 · 复现实验" \
  ./bin/burntoken burn --preset math -n 4 -P 2 --seed 42
# 预期：每次跑的 4 条 prompt 顺序一致
