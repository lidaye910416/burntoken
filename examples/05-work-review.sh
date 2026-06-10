#!/usr/bin/env bash
# =============================================================
#  05-work-review.sh
#  演示：work 子任务，让模型真干活的 review
#  8 个内置 task：review / docs / tests / refactor / explain
#                / summarize / commit / translate
#
#  使用：
#    ./examples/05-work-review.sh
#
#  跟 burn / repl 的区别：
#    - burn / repl：合成 prompt 烧 token，输出不一定有用
#    - work：拿真实代码喂给模型，让它做 review / 写测试 / 加文档
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
[ -f .env ] && { set -a; source .env; set +a; }

# 0) 准备一个待 review 的小文件
TMP="$(mktemp -d)"
cat > "$TMP/sample.py" <<'PY'
# 简单的字符串处理
def to_snake(name):
    out = ''
    for c in name:
        if c.isupper():
            out = out + '_' + c.lower()
        else:
            out = out + c
    return out.lstrip('_')

def to_camel(name):
    parts = name.split('_')
    return parts[0] + ''.join(p.title() for p in parts[1:])

def main():
    print(to_snake('HelloWorld'))
    print(to_camel('hello_world'))

if __name__ == '__main__':
    main()
PY
echo "Demo file: $TMP/sample.py"

# 1) 单文件 review：写到 out-dir/，同时打到终端
echo
echo "--- 1) work review 单文件 ---"
./bin/burntoken work review "$TMP/sample.py" \
    --show --out-dir out/work-review-demo
# 预期（节选）：
# ● task=review  model=hbscloud-glm
#   → 1 个文件 / 任务
# work/review |██████████████████████| 1/1 100.0% elapsed= 4.1s
# ┌─ hbscloud-glm · sample.py
# │ ## 1. 🐞 Bug 风险
# │ - to_camel("") 会因 parts[0] 没问题而直接返回 ''，但语义模糊（OK）
# │ - to_snake("XMLHttpRequest") → "_x_m_l_http_request"，不符合预期
# │
# │ ## 2. 🔒 安全问题
# │ - 无
# │
# │ ## 3. ⚡ 性能
# │ - 字符串拼接用 + 而非 join，大循环会慢
# │
# │ ...
# │ ## 6. ✅ 必须改（高优先级）
# │ - 修 XMLHttpRequest 这种连续大写：应识别为单词边界
# │ - 字符串拼接改 ''.join([...])
# └─ prompt=412 completion=782 total=1194 latency=4103ms
# ✓ 1 份输出已写到：out/work-review-demo/

# 2) 同时存 jsonl：每条结果可被脚本消费
echo
echo "--- 2) work review + 落 jsonl ---"
./bin/burntoken work review "$TMP/sample.py" \
    --save logs/work-review.jsonl
# 预期 logs/work-review.jsonl 多 1 行：
# {"type":"work","task":"review","path":".../sample.py","model":"hbscloud-glm",
#  "text":"## 1. 🐞 Bug 风险 ...","usage":{...},"latency_ms":4103}

# 3) 喂 stdin：把 git diff 灌进 review
echo
echo "--- 3) 喂 stdin ---"
cat "$TMP/sample.py" | ./bin/burntoken work review -
# 预期：- 表示从 stdin 读，等价于 work review <file>，但路径在结果里是 <stdin>

# 4) 真实场景：review 自己 client.py（高 token，长输出）
echo
echo "--- 4) review burntoken/client.py（真实场景） ---"
./bin/burntoken work review burntoken/client.py \
    --max-tokens-per-file 4096 \
    --out-dir out/client-review
# 预期：~30k-60k prompt token（看模型），~3-4k completion，
# 输出文件 out/client-review/review__burntoken_client.py.md

# 5) 批量：review 一个目录，2 并发
echo
echo "--- 5) review burntoken/ 整个包，2 并发 ---"
./bin/burntoken work review burntoken/ --ext py -P 2 \
    --out-dir out/burntoken-review
# 预期：进度条，~10-15 个 .py 文件，最后打印
# ✓ N 份输出已写到：out/burntoken-review/

# 6) 限制成本：review 一个大库，烧到 ¥0.50 自动停
echo
echo "--- 6) 熔断：成本 ≤ ¥0.50 ---"
HBS_PRICE_PROMPT=0.001 HBS_PRICE_COMPLETION=0.002 \
  ./bin/burntoken work review burntoken/ --ext py -P 4 \
    --max-cost 0.5 --out-dir out/burntoken-review-capped
# 预期：跑到 ¥0.50 左右触发熔断，已跑完的写入 out/，剩余跳过

# 7) work 子任务对照（同名子命令）
echo
echo "--- 7) work tests / docs / explain / refactor ---"
./bin/burntoken work tests  "$TMP/sample.py" --out-dir out/work-tests
./bin/burntoken work docs   "$TMP/sample.py" --out-dir out/work-docs
./bin/burntoken work explain "$TMP/sample.py" --show
./bin/burntoken work refactor "$TMP/sample.py" --out-dir out/work-refactor
# 预期：每个 task 都产一份 .md，路径形如
#   out/work-tests/tests__sample.py.md
#   out/work-docs/docs__sample.py.md
#   out/work-refactor/refactor__sample.py.md
