#!/usr/bin/env bash
# =============================================================
#  01-single-call.sh
#  演示：单条 prompt 调用 hbscloud（最常用的入口）
#
#  使用：
#    chmod +x examples/01-single-call.sh
#    ./examples/01-single-call.sh
#
#  跑这个脚本会真的发请求。注释里是 hbscloud 的真实回包样式。
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 加载 .env（bin/burntoken 也会自己 source，这里再 source 一次方便 echo）
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# 1) 闲聊：单行 prompt
echo "--- 1) 闲聊 ---"
./bin/burntoken -p "用一句话说 hello"
# 预期输出（节选）：
# ┌─ hbscloud-glm
# │ 你好，世界！有什么可以帮你的吗？
# └─ prompt=18 completion=14 total=32 latency=812ms

# 2) 指定模型 + system + max_tokens
echo "--- 2) 解数学题 + 限长 ---"
./bin/burntoken -p "求 ∫(0,1) x^2 dx = ?" \
    --model hbscloud-deepseek \
    --system "你是严谨的数学家，请一步步推理。" \
    --max-tokens 256
# ┌─ hbscloud-deepseek
# │ ∫₀¹ x² dx = [x³/3]₀¹ = 1/3。
# │ 详细过程：原函数 F(x) = x³/3，代入上下限 1 和 0 相减即得 1/3。
# └─ prompt=42 completion=58 total=100 latency=1340ms

# 3) 显式调 run 子命令（不带 -p 时，行为和上面一致）
echo "--- 3) 显式 run 子命令 ---"
./bin/burntoken run -p "推荐一道简单的家常菜" --max-tokens 64
# ┌─ hbscloud-glm
# │ 番茄炒蛋：3 个鸡蛋打散，2 个番茄切块，热油翻炒 3 分钟即可。
# └─ prompt=20 completion=42 total=62 latency=687ms

# 4) 错误示范：缺 API key
echo "--- 4) 缺 API key 时的提示 ---"
HBS_API_KEY="" ./bin/burntoken -p "hi" || true
# ✗ HBS_API_KEY 未设置，请检查 .env

# 5) 落盘：把这次调用写进 jsonl
echo "--- 5) 落盘 ---"
./bin/burntoken -p "用 Python 写一个回文判断函数" \
    --model hbscloud-glm \
    --max-tokens 256 \
    --save logs/single-call.jsonl
# 调用完成后，logs/single-call.jsonl 多一行：
# {"type":"chat","model":"hbscloud-glm","text":"def is_palindrome(s): ...","usage":{"prompt_tokens":21,"completion_tokens":86,"total_tokens":107},"latency_ms":923,"finish_reason":"stop"}
