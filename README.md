# burntoken · hbscloud Token 燃烧器

[![CI](https://img.shields.io/github/actions/workflow/status/lidaye910416/burntoken/ci.yml?branch=main&label=ci&logo=github)](https://github.com/lidaye910416/burntoken/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)

> 直接调 hbscloud（OpenAI 兼容协议）来**消耗 Token** 的独立 CLI。
> **不再依赖 Claude Code、不再依赖 LiteLLM、不再依赖任何代理进程。**

**Project status: active** — 维护中，接受 issue / PR。

## 目录

- [架构](#架构)
- [安装](#安装)
- [配置](#配置)
- [模式总览](#模式总览)
- [用法](#用法)
- [文件结构](#文件结构)
- [高级](#高级)
- [常见问题](#常见问题)
- [Troubleshooting](#troubleshooting)
- [burntoken-review-tribunal](#burntoken-review-tribunal-大型审判团)

## 架构

```
┌─────────────┐   HTTP/SSE    ┌────────────────┐
│  burntoken (CLI) │ ────────────▶ │ model.hbscloud │
│  本进程     │ ◀──────────── │  /v1/chat/...  │
└─────────────┘               └────────────────┘
```

一个 Python 包 + 一个 shell 包装。零后台进程、零代理、零证书。

## 安装

```bash
cd ~/burntoken
make install
source ~/.zshrc
```

会做三件事：
1. `pip install httpx`
2. 把 `bin/` 加入 PATH（直接 `burntoken` 命令可用）
3. 复制 `.env.example → .env`（**填入 `HBS_API_KEY`**）

## 配置

```bash
$EDITOR ~/burntoken/.env
# 必填：HBS_API_KEY
# 可选：HBS_BASE_URL（默认 https://model.hbscloud.com.cn/v1）
# 可选：HBS_MODEL（默认 gpt-3.5-turbo；先用 `burntoken --models` 查实际名）
# 可选：HBS_PRICE_PROMPT / HBS_PRICE_COMPLETION（每 1k token 的价格，用于成本统计）
```

## 模式总览

burntoken 有 **5 层可切换模式**，按作用域从大到小排：

### 1. 子命令模式（10 个；决定做什么）

| 子命令 | 用途 | 是否真烧 |
|--------|------|---------|
| `run`（默认） | 单条调用 | ✓ |
| `burn` | 批量烧 token（-n 次数 -P 并发） | ✓ |
| `repl` | 交互 REPL（`/usage` `/reset` `/quit`） | ✓ |
| `models` | 列出已配置 provider 上的模型 | 只读 |
| `config` | show / init / path（管理 .env 与 config） | 不调 API |
| `providers` | 列出所有 provider | 不调 API |
| `use <name>` | 切换默认 provider（写到 `~/.config/burntoken/active`） | 不调 API |
| `team` | 多 agent 流水线（Strategist→Dispatcher→Accountant→Reviewer） | ✓ |
| `review` | 全项目 review：本地路径 / `github:user/repo` / URL | ✓ |
| `work` | 真实任务（review/docs/tests/refactor/explain/...） | ✓ |

详见 `burntoken <cmd> --help` 或下文 [用法](#用法)。

### 2. Preset 模式（5 个；决定 prompt 风格与 max_tokens）

| preset | 默认 max_tokens | 用途 |
|--------|----------------|------|
| `chat` | 128 | 短答闲聊 |
| `math` | 512 | 推理题 |
| `code` | 768 | 代码生成 |
| `essay` | 2048 | 长文输出 |
| `longctx` | 512 | 长上下文（用 `--multi-turn N` 灌 N 轮历史） |

用 `--preset <name>` 选择。

### 3. 行为 flag（决定单次调用怎么跑）

| flag | 效果 |
|------|------|
| `--stream` | SSE 流式输出（边收边打） |
| `--save PATH` | 把每条结果追加到 JSONL（完整 text + usage） |
| `--log-file PATH` | 把每次调用的结构化事件写到 JSONL（run_id / tokens / cost / error） |
| `--max-tokens N` | **熔断**：累计 token ≥ N 自动停 |
| `--max-cost X` | **熔断**：累计成本 ≥ X 自动停（需设 HBS_PRICE_*） |
| `--multi-turn N` | longctx 模式：塞入 N 轮 user/assistant 历史 |
| `--seed N` | 固定随机种子 → prompt 可复现 |
| `--repl` | 进 REPL 循环 |
| `--log-file PATH` | 顶层 flag：所有子命令的调用都走 JSONL 事件流 |

### 4. Example 脚本模式（决定 examples/*.sh 怎么跑）

**`examples/03-batch-burn.sh` 的双模式**：

| 模式 | 调用方式 | 行为 |
|------|---------|------|
| `demo`（**默认**） | `./examples/03-batch-burn.sh` 或 `./examples/03-batch-burn.sh demo` | 干跑（dry-run）：只打印 `./bin/burntoken ...` 命令，不真发请求 |
| `confirm` | `./examples/03-batch-burn.sh confirm` | 真烧：检查 `HBS_API_KEY`、给 3 秒反悔窗口、然后实跑全部 8 段 |

> 设计原则：examples/ 脚本**默认 dry-run**。要真烧必须显式写 `confirm`，避免误操作烧 token。

### 5. Env / Provider 模式（决定底层怎么连）

| 变量 | 用途 | 默认 |
|------|------|------|
| `HBS_API_KEY` | API 必填 key | （必填） |
| `HBS_BASE_URL` | provider base URL | `https://model.hbscloud.com.cn/v1` |
| `HBS_MODEL` | 默认模型 | （空 → 走 provider 默认） |
| `HBS_VERIFY` | TLS 证书校验 | `false`（启动 banner 会提示） |
| `HBS_PRICE_PROMPT` / `HBS_PRICE_COMPLETION` | 每 1k token 价格（CNY/USD 自定） | `0`（不计算） |
| `BURNTOKEN_CONFIG` | 配置文件路径（providers 多 provider 模式） | `~/.config/burntoken/config.yaml` |
| `BURNTOKEN_CACHE_DIR` | review/work 子命令的本地缓存目录 | `~/.cache/burntoken` |

**Provider 类型**（`providers/`）：
- `openai`（默认，OpenAI 兼容协议，覆盖 hbscloud / OpenAI / 其他兼容端点）
- `anthropic`（Anthropic Messages API）

**`burntoken team --mode`**（Agent 流水线模式）：
- `meaningful` — 任务有意义，每个 agent 真干活
- `pointless` — 任务无意义，刻意烧 token
- `mixed` — 混合

---

## 用法

### 1. 单条

```bash
burntoken -p "用一句话说 hello"
burntoken -p "写首七言绝句" --stream
burntoken -p "Solve x^2=9" --model deepseek-reasoner
burntoken -p "..." --system "你是英语老师" --max-tokens 1024
```

### 2. 批量烧（推荐用来**烧 Token**）

```bash
# 烧 20 次 code 任务，4 个并发
burntoken burn --preset code -n 20 -P 4

# 烧长上下文，灌 10 轮历史，8 并发，100 条
burntoken burn --preset longctx --multi-turn 10 -n 100 -P 8

# 熔断：总 token 超过 50k 自动停 / 总成本超过 ¥5 自动停
burntoken burn --preset essay -n 1000 -P 8 --max-tokens 50000 --max-cost 5.0
```

5 个内置 preset：

| name      | 用途          | max_tokens |
| --------- | ----------- | ---------- |
| `chat`    | 闲聊短答         | 128        |
| `math`    | 推理题          | 512        |
| `code`    | 代码生成         | 768        |
| `essay`   | 长文输出         | 2048       |
| `longctx` | 长上下文（灌 N 轮历史） | 512        |

### 3. 交互 REPL

```bash
burntoken --repl
# » 你好
# ┌─ gpt-3.5-turbo
# │ 你好！有什么可以帮你？
# └─ prompt=22 completion=10 total=32 latency=823ms
# » /usage     # 看累计 token
# » /reset     # 清空对话
# » /quit
```

### 4. 真实任务烧（让模型真干活）

```bash
# 单文件：code review
burntoken work review burntoken/client.py
burntoken work review burntoken/client.py --show          # 同时打到终端
burntoken work explain burntoken/client.py --out-dir docs/

# 目录批量：2 并发，输出到 reviews/
burntoken work review burntoken/ --ext py -P 2 --out-dir reviews/

# git diff：根据 staged 改动写 commit message
burntoken work commit --git staged
burntoken work review --git working

# 限制成本
burntoken work docs burntoken/ --ext py -P 4 --max-cost 5.0

# 喂 stdin
cat foo.py | burntoken work review -
```

8 个内置任务：

| task        | 用途                | 适合模型        |
| ----------- | ----------------- | ----------- |
| `review`    | 列 bug/安全/性能/风格    | 长输出（~4k）   |
| `docs`      | 给函数/类补 docstring | 长输出         |
| `tests`     | 生成 pytest 单元测试   | 长输出         |
| `refactor`  | 提重构 + BEFORE/AFTER | 长输出         |
| `explain`   | 逐段解释（教学用）         | 长输出         |
| `summarize` | 200 字总结           | 短输出         |
| `commit`    | git diff → conventional commit | 短输出 |
| `translate` | 翻译注释到英文           | 长输出         |

输入源（自动检测）：
- `path/*.py` — 文件 / 目录 / glob
- `--git staged|working|branch:NAME|range:SPEC`
- `-` — stdin

每个文件的输出默认写到 `--out-dir`，文件名 `{task}__{path_as_filename}.md`。
同时支持 `--save run.jsonl` 把全部结果落 jsonl。

### 5. 实战案例：拿 MiroFish 当库烧

> **场景**：你下载了 [MiroFish](https://github.com/666ghj/MiroFish) 群体智能引擎到 `~/MiroFish`，下面用它把 `burntoken` 的所有命令走一遍。

#### 5.1 摸体量

```bash
$ find ~/MiroFish -name "*.py" -not -path "*/.venv/*" | wc -l
37
$ wc -l ~/MiroFish/backend/app/api/simulation.py
2716 simulation.py
```

→ 37 个 .py 文件集中在 `backend/app/api/` 和 `backend/app/services/`，最大单文件 2716 行。

#### 5.2 全量 review（最常用）

```bash
$ cd ~/burntoken
$ ./bin/burntoken review ~/MiroFish/backend --ext py -P 4 \
    --max-tokens 150000 --max-tokens-per-file 2048 \
    --out-dir out/mirofish-review
```

实测输出：

```
● review · local · backend · /Users/jasonlee/MiroFish/backend
  → out_dir = out/mirofish-review/local__backend
● task=review  model=hbscloud-glm
  → 35 个文件 / 任务
work/review |███████████████████░░░| 23/35  65.7% ...
⚠ 熔断：tokens 150,226 ≥ 150,000
════════════════════════════════════════════════════════════
  burntoken 完成 · model=hbscloud-glm
════════════════════════════════════════════════════════════
  请求             20/20  (failed=0)
  prompt tok     115,714
  completion     34,512
  total tok      150,226
  耗时             341.42s
  吞吐             101.08 tok/s
════════════════════════════════════════════════════════════
✓ 35 份输出已写到：out/mirofish-review/local__backend/
```

→ 5.7 分钟烧 **150,226 tokens**，0 失败，35 份 .md review 落盘。最大单文件 simulation_manager.py 找出 3 个真 bug（状态反序列化脆弱、Twitter vs Reddit profile 格式不一致、硬编码 scripts 路径）。

#### 5.3 单文件精读（`work` 子任务）

```bash
# 解释 oassis profile 生成器
$ ./bin/burntoken work explain ~/MiroFish/backend/app/services/oasis_profile_generator.py --show

# 给 simulation.py 写单测
$ ./bin/burntoken work tests ~/MiroFish/backend/app/api/simulation.py

# 给 report_agent.py 加文档
$ ./bin/burntoken work docs ~/MiroFish/backend/app/services/report_agent.py \
    --out-dir out/mirofish-docs

# 提重构建议
$ ./bin/burntoken work refactor ~/MiroFish/backend/app/services/zep_tools.py -P 4
```

每条 1 次 LLM 调用，~2-5k tokens/次。8 种 task 选：`review` / `docs` / `tests` / `explain` / `refactor` / `summarize` / `commit` / `translate`。

#### 5.4 多 agent 流水线（4× 倍率）

```bash
$ ./bin/burntoken team --mode meaningful -P 4 --max-tokens-per-file 8192
# Strategist → Dispatcher → Accountant → Reviewer
# 每个文件被 4 个 agent 各调 1 次
# 默认 10 轮 ≈ 40 次 LLM 调用 ≈ 12 万 tokens
```

⚠️ `team` **不接 path 参数** —— 任务由 Strategist 内部生成。想烧特定库用 5.2 的 `review`。

#### 5.5 GitHub 仓库（自动 clone 到缓存）

```bash
$ ./bin/burntoken review github:666ghj/MiroFish --ext py -P 4 \
    --max-tokens 200000 --max-tokens-per-file 2048
# 不用自己 git clone
```

#### 5.6 批量合成 prompt（最便宜的烧法）

```bash
$ ./bin/burntoken burn --preset code -n 50 -P 8 --max-cost 1.0
# 50 条 code 任务，8 并发
```

5 个内置 preset：`chat` (短答) / `math` (推理) / `code` (代码) / `essay` (长文) / `longctx` (灌长历史)。

#### 5.7 交互 REPL（边读边问）

```bash
$ ./bin/burntoken --repl
● burntoken REPL · model=hbscloud-glm · /quit 退出 /reset 清空 /usage 统计
» MiroFish 的 SimulationStatus 有几种状态？
┌─ hbscloud-glm
│ SimulationStatus 枚举包含: created / running / paused / completed / failed
└─ prompt=2847 completion=215 total=3062 latency=1247ms
» /usage
📊 usage: prompt=3147  completion=448  total=3595
» /quit
```

#### 5.8 不限成本 · 最大化烧

```bash
# 单次最猛：16 并发 + 8k 单文件输出 + 几乎无熔断
$ ./bin/burntoken review ~/MiroFish --ext py -P 16 \
    --max-tokens-per-file 8192 --max-bytes 500000 --max-tokens 99999999

# 真·无上限：while true 循环
$ while true; do
    ./bin/burntoken team --mode mixed -P 16 --max-tokens-per-file 8192
    ./bin/burntoken review ~/MiroFish --ext py -P 16 --max-tokens 99999999
  done
# 唯一熔断 = Ctrl-C
```

#### 5.9 MiroFish 速查表

| 想干嘛 | 命令 |
|---|---|
| 问一条问题 | `burntoken -p "..."` |
| 流式输出 | `burntoken -p "..." --stream` |
| 全量 review 库 | `burntoken review <path> --ext py -P 4` |
| 单文件 review | `burntoken work review <file.py>` |
| 给文件写测试 | `burntoken work tests <file.py>` |
| 加文档 | `burntoken work docs <file.py> --out-dir out/` |
| 解释文件 | `burntoken work explain <file.py> --show` |
| 多 agent 分析 | `burntoken team --mode meaningful -P 4` |
| 烧 GitHub 库 | `burntoken review github:user/repo` |
| 批量合成 | `burntoken burn --preset code -n 50 -P 8` |
| 交互 | `burntoken --repl` |
| 列模型 | `burntoken --models` |
| 列 provider | `burntoken --providers` |
| 切 provider | `burntoken use hbscloud` |
| e2e 自检 | `make test` |
| **无上限烧** | `while true; do burntoken review <path> --ext py -P 16; done` |

> 💡 换库？把 `~/MiroFish` 换掉就行。所有命令通用。

### 6. Examples（可执行的 demo）

> 6 个**自包含的、注释里贴了 hbscloud 真实回包样式的 demo**——
> 不确定一个命令会输出啥时，先看 `examples/` 里的预期，再决定跑不跑。

```bash
cd ~/burntoken
chmod +x examples/*.sh
./examples/00-version.sh             # 装好之后先跑：版本自检（不调 API）
./examples/01-single-call.sh         # 单条 prompt
./examples/02-streaming.sh           # 流式输出
./examples/03-batch-burn.sh          # 批量烧 + 熔断（加 demo 子参数仅打印命令）
./examples/04-repl-session.txt       # REPL 真实记录（仅展示）
./examples/05-work-review.sh         # work 子任务：review / docs / tests
./examples/06-models-list.txt        # --models / config show（仅展示）
```

完整索引 + 排错指引见 **[`examples/README.md`](examples/README.md)**。

### 7. 落盘

```bash
burntoken burn --preset code -n 50 -P 4 --save logs/burntoken.jsonl
# 每条调用结果会追加到 jsonl：{type, idx, model, text, usage, latency_ms}
```

### 8. 查模型

```bash
burntoken --models
# ✓ 12 个模型 @ https://model.hbscloud.com.cn/v1:
#   - gpt-4o  (openai)
#   - claude-3-5-sonnet  (anthropic)
#   ...
```

## 文件结构

```
burntoken/
├── burntoken/                  ← 主程序包
│   ├── __init__.py
│   ├── __main__.py        # python -m burntoken
│   ├── cli.py             # argparse
│   ├── client.py          # 同步 + 异步 + 流式 API 客户端
│   ├── tracker.py         # token / 成本 / 性能计数（线程安全）
│   ├── presets.py         # 5 种烧法
│   └── reporter.py        # 终端输出（流式 / 进度条 / 汇总）
├── bin/burntoken               # shell 包装
├── legacy/                ← 旧的 LiteLLM 代理（已弃用）
│   ├── hbsproxy.py
│   ├── litellm_config.yaml
│   ├── test_proxy.py
│   ├── bin/{ccgsc,proxy-only}
│   └── install.sh
├── .env / .env.example
├── requirements.txt
├── install.sh
├── Makefile
└── README.md
```

## 高级

### 改单次调用的所有参数

```bash
burntoken -p "..." \
  --model deepseek-reasoner \
  --temperature 0.2 \
  --max-tokens 4096
```

### 用作 Python 库

```python
from burntoken.client import HBSClient, ChatMessage

with HBSClient(api_key="sk-...") as c:
    resp = c.chat(
        [ChatMessage("user", "hi")],
        model="gpt-4o",
        max_tokens=128,
    )
    print(resp.text, resp.usage)
```

并发：

```python
import asyncio
from burntoken.client import AsyncHBSClient, ChatMessage

async def main():
    async with AsyncHBSClient(api_key="sk-...", concurrency=8) as c:
        tasks = [
            c.chat([ChatMessage("user", f"q{i}")], model="gpt-4o", max_tokens=64)
            for i in range(20)
        ]
        for r in asyncio.as_completed(tasks):
            resp = await r
            print(resp.text, resp.usage)

asyncio.run(main())
```

## 常见问题

### Q: 跟旧版（LiteLLM + Claude Code）比，差别在哪？
A: 旧版是给 Claude Code 套一层代理，把 Anthropic 协议翻译成 OpenAI 协议。
新版直接调 hbscloud，少了代理层、少了证书、少了 Claude Code 依赖。
**没有 Claude Code 也能用**——这正是 `burntoken` 的目的。

### Q: 怎么彻底切到 burntoken？
```bash
# 1. 编辑 .env
$EDITOR ~/burntoken/.env

# 2. 把 HBS_MODEL 设成你想要的模型
HBS_MODEL=deepseek-reasoner

# 3. 试一下
burntoken --models                  # 看看支持哪些模型
burntoken -p "hi" --max-tokens 16   # 试发一条
burntoken burn --preset code -n 5 -P 2  # 烧 5 次
```

### Q: 想删掉旧 LiteLLM 文件
```bash
rm -rf ~/burntoken/legacy
```

### Q: 报 `[401] invalid api key`
去 hbscloud 控制台生成新 Key，编辑 `.env` 重试。

### Q: 报 SSL / 证书错误
一般是公司网络代理。设一下：
```bash
export HTTPS_PROXY=http://your-proxy:8080
```
或临时给 httpx 传 `proxies=...`。

### Q: 启动时看到 `HBS TLS verify: off`
默认 `HBS_VERIFY=false`（关闭 TLS 证书校验，方便公司代理 / 自签证书 / 中间人环境使用）。  
首次启动时会打印一行 banner 提示当前状态（`--batch` 模式下不打印）。

需要打开校验时：
```bash
export HBS_VERIFY=true
burntoken --models
# 启动 banner 会变成: HBS TLS verify: on
```

`.env` 里也已经默认是 `HBS_VERIFY=false`，可在 `~/burntoken/.env` 中修改。

---

## Troubleshooting

> 自查清单。遇到报错先扫一眼这里，90% 的问题都能 30 秒内定位。

### 1. SSL 校验失败 / `HBS_VERIFY` 相关

**症状：**
- `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed`
- 启动 banner 提示 `HBS TLS verify: off`，想打开校验
- 公司代理 / 自签证书 / 中间人环境请求被拒

**修复：**
- 关闭校验（默认就是关）：`export HBS_VERIFY=false` 或在 `.env` 设 `HBS_VERIFY=false`
- 打开校验（仅在你能信任证书链时）：`export HBS_VERIFY=true`，banner 会变成 `HBS TLS verify: on`
- 走公司代理：`export HTTPS_PROXY=http://your-proxy:8080`

### 2. 报 `HBS_API_KEY 未设置` / `[401] invalid api key`

**症状：**
- 启动时红字打印 `✗ HBS_API_KEY 未设置，请检查 .env`
- 请求返回 `401 invalid api key` 或 `401 Incorrect API key provided`

**修复：**
```bash
# 1. 确认 .env 存在
ls -la ~/burntoken/.env

# 2. 填入 Key
$EDITOR ~/burntoken/.env
# HBS_API_KEY=sk-...

# 3. 验证
burntoken --models          # 能列出模型就是 OK
```

Key 失效就去 [hbscloud 控制台](https://model.hbscloud.com.cn) 重新签发一个。环境变量也可以临时覆盖：
```bash
export HBS_API_KEY=sk-新key
burntoken -p "hi"
```

### 3. `ModuleNotFoundError: No module named 'httpx'`

**症状：**
- `ModuleNotFoundError: No module named 'httpx'`
- `ImportError: cannot import name 'httpx'`

**修复：**
```bash
cd ~/burntoken
make install            # 包含 pip install httpx
# 或手动：
pip install httpx
# 验证：
python3 -c "import httpx; print(httpx.__version__)"
```

### 4. `burntoken: command not found`（安装后 PATH 没更新）

**症状：**
- `zsh: command not found: burntoken`
- `make install` 跑成功了但 `which burntoken` 没输出

**修复：**
```bash
# 1. 确认 bin 目录存在
ls ~/burntoken/bin/burntoken

# 2. 让当前 shell 重新读 .zshrc（make install 会自动追加 PATH，但新 shell 才会生效）
source ~/.zshrc
# bash 用户：
source ~/.bashrc

# 3. 验证
which burntoken        # 应输出 ~/burntoken/bin/burntoken
burntoken --version

# 4. 永久方案：手动把 PATH 写进 shell rc
echo 'export PATH="$HOME/burntoken/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 5. 模型名 404：`The model XXX does not exist`

**症状：**
- `404 · The model 'gpt-4o' does not exist`
- 同样的代码在别的 CLI 跑得通，到 burntoken 就 404

**修复：**
hbscloud 的**真实模型名**经常和 OpenAI 官方名不一样。先列出来再选：
```bash
burntoken --models
# ✓ 12 个模型 @ https://model.hbscloud.com.cn/v1:
#   - hbscloud-glm
#   - deepseek-reasoner
#   - gpt-3.5-turbo
#   ...

# 把看到的名字填进 .env
HBS_MODEL=hbscloud-glm
# 或单次指定
burntoken -p "hi" --model hbscloud-glm
```

### 6. 429 限流 / 自动重试

**症状：**
- 偶发 `[429] Rate limit reached for requests`
- 批量时看到 `retryable: 429` 然后自动恢复
- 长时间跑后吞吐断崖下跌

**修复：**
burntoken 内置了**指数退避重试**（`client.py` 里 `retry_backoff=1.5`）：遇到 429 / 5xx 会自动按 `1.5^attempt` 秒退避并重试。无需手动操作。

- 持续触发限流：降并发 `-P 2`（或更小）
- 想要"宁可失败也不等"：传 `--max-tokens` / `--max-cost` 提前熔断
- 大量重试仍失败：检查 Key 是否在控制台被临时限流

### 7. 批量跑到一半被 `--max-cost` 熔断

**症状：**
- `⚠ 熔断：cost 5.0123 ≥ 5.0000` 之后程序退出
- 1000 条任务只跑了几十条就停了

**修复：**
这是**预期行为**，不是 bug。`--max-cost` 触底自动停，避免账单爆炸。
```bash
# 想跑完：把阈值抬高
burntoken burn --preset code -n 1000 -P 8 --max-cost 50.0

# 想真·无熔断：不传该参数
burntoken burn --preset code -n 1000 -P 8

# 想看每条花多少钱：--save 落盘 jsonl
burntoken burn --preset code -n 100 -P 4 --max-cost 1.0 --save logs/burn.jsonl
```

### 8. 报错信息去哪看 / 日志在哪

**位置：**

| 输出 | 落点 |
|---|---|
| 普通进度 / 错误 / 状态 | **stderr**（终端红色字） |
| 正常回复（单条） | **stdout**（可 `\| less` / `\| tee`） |
| `--save logs/xxx.jsonl` | 自定义 jsonl，**每条调用一行** `{type, idx, model, text, usage, latency_ms, ts}` |
| 启动 banner（`HBS TLS verify: ...`） | stderr，**仅在交互式终端**（`--batch` / pipe 模式不打印） |
| 旧 LiteLLM 代理日志（如果还留着 `legacy/`） | `~/burntoken/logs/proxy.log`（新版不写） |

**调试建议：**
```bash
# 看完整错误
burntoken -p "hi" 2>&1 | cat

# 分流 stderr 到文件
burntoken -p "hi" 2>logs/err.log

# 跑完看落盘 jsonl
burntoken burn --preset code -n 20 -P 4 --save logs/run.jsonl
less logs/run.jsonl
```

---

## burntoken-review-tribunal (大型审判团)

对 burntoken 项目自身做 exhaustive 代码审查 + 烧 token 的 workflow 脚本（Node.js 实现，与上面 burntoken CLI 并列）。

7 个独立审查视角（lens）× 3 个对抗性裁判（judge）× 多轮循环到枯竭，详见：
- 设计: `docs/superpowers/specs/2026-06-06-burntoken-review-tribunal-design.md`
- 实施计划: `docs/superpowers/plans/2026-06-06-burntoken-review-tribunal.md`
- Skill: `.claude/skills/burntoken-review-tribunal/SKILL.md`

```bash
# 跑
node .claude/workflows/burntoken-review-tribunal.js --target burntoken/

# 测
npm test
```
