#!/usr/bin/env bash
# =============================================================
#  02-streaming.sh
#  演示：流式输出（SSE, OpenAI 兼容 /chat/completions?stream=true）
#
#  使用：
#    ./examples/02-streaming.sh
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
[ -f .env ] && { set -a; source .env; set +a; }

# 流式 vs 非流式：
#   - 体感：非流式要等整段生成完；流式一边生成一边往终端推
#   - 内部：bin/burntoken 走 client.stream_chat()，每收一个 SSE chunk 就
#     print_stream_chunk() 写一行，回包是逐 token 推进
#   - 适用：长输出（>512 token），比如 essay / code / review

# 1) 基础流式
echo "--- 1) 流式：写一段 200 字短评 ---"
./bin/burntoken -p "用 200 字评论 AI 与教育的关系" --stream
# 预期（节选，按时间顺序，token 逐个推）：
# ● hbscloud-glm (max_tokens=1024)
# AI 与教育正在深度融合：一方面，AI 可以
# 作为个性化辅导老师，根据学生的薄弱环节推
# 荐练习题；另一方面，AI 也让"获取知识"这件
# 事的边际成本趋近于零。  ↳ prompt=21 completion=187 total=208 latency=2210ms
# （最后一行是收尾的 dim 灰色 token 汇总）

# 2) 流式 + 大 max_tokens（长文）
echo "--- 2) 流式：长文（2048 token） ---"
./bin/burntoken -p "以'城市的雨夜'为题写 300 字散文" \
    --stream --max-tokens 2048 --model hbscloud-glm
# 预期：终端连续滚字约 5-8 秒。流式体感明显，
# 因为 completion 上来就开始喷，不必等整段。

# 3) 落盘流式结果
echo "--- 3) 流式 + 落 jsonl ---"
./bin/burntoken -p "推荐一部 2024 年的科幻电影，2 句话" \
    --stream --max-tokens 128 --save logs/stream.jsonl
# 落盘里只会有一条 record：
#   {"type":"stream","model":"hbscloud-glm","text":"《沙丘2》延续第一部...",
#    "usage":{"prompt_tokens":19,"completion_tokens":48,"total_tokens":67},
#    "latency_ms":740}

# 4) 拿 Python API 直接拿流（更细粒度）
echo "--- 4) Python API 拿流 ---"
python3 - <<'PY'
from burntoken.client import HBSClient, ChatMessage
with HBSClient() as c:
    for d in c.stream_chat(
        [ChatMessage("user", "用 Python 写一个二分查找，1 句注释")],
        model="hbscloud-glm", max_tokens=200,
    ):
        if d.content:
            print(d.content, end="", flush=True)
    print()
# 预期：
# def binary_search(arr, target):
#     lo, hi = 0, len(arr) - 1
#     while lo <= hi:
#         mid = (lo + hi) // 2
#         if arr[mid] == target: return mid
#         ...
PY
