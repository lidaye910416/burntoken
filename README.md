# burn · hbscloud Token 燃烧器

> 直接调 hbscloud（OpenAI 兼容协议）来**消耗 Token** 的独立 CLI。
> **不再依赖 Claude Code、不再依赖 LiteLLM、不再依赖任何代理进程。**

## 架构

```
┌─────────────┐   HTTP/SSE    ┌────────────────┐
│  burn (CLI) │ ────────────▶ │ model.hbscloud │
│  本进程     │ ◀──────────── │  /v1/chat/...  │
└─────────────┘               └────────────────┘
```

一个 Python 包 + 一个 shell 包装。零后台进程、零代理、零证书。

## 安装

```bash
cd ~/claude-code-hbscloud
./install.sh
source ~/.zshrc
```

会做三件事：
1. `pip install httpx`
2. 把 `bin/` 加入 PATH，写入 `alias burn=...`
3. 复制 `.env.example → .env`（**填入 `HBS_API_KEY`**）

## 配置

```bash
$EDITOR ~/claude-code-hbscloud/.env
# 必填：HBS_API_KEY
# 可选：HBS_BASE_URL（默认 https://model.hbscloud.com.cn/v1）
# 可选：HBS_MODEL（默认 gpt-3.5-turbo；先用 `burn --models` 查实际名）
# 可选：HBS_PRICE_PROMPT / HBS_PRICE_COMPLETION（每 1k token 的价格，用于成本统计）
```

## 用法

### 1. 单条

```bash
burn -p "用一句话说 hello"
burn -p "写首七言绝句" --stream
burn -p "Solve x^2=9" --model deepseek-reasoner
burn -p "..." --system "你是英语老师" --max-tokens 1024
```

### 2. 批量烧（推荐用来**烧 Token**）

```bash
# 烧 20 次 code 任务，4 个并发
burn --burn --preset code -n 20 -P 4

# 烧长上下文，灌 10 轮历史，8 并发，100 条
burn --burn --preset longctx --multi-turn 10 -n 100 -P 8

# 熔断：总 token 超过 50k 自动停 / 总成本超过 ¥5 自动停
burn --burn --preset essay -n 1000 -P 8 --max-tokens 50000 --max-cost 5.0
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
burn --repl
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
burn work review burn/client.py
burn work review burn/client.py --show          # 同时打到终端
burn work explain burn/client.py --out-dir docs/

# 目录批量：2 并发，输出到 reviews/
burn work review burn/ --ext py -P 2 --out-dir reviews/

# git diff：根据 staged 改动写 commit message
burn work commit --git staged
burn work review --git working

# 限制成本
burn work docs burn/ --ext py -P 4 --max-cost 5.0

# 喂 stdin
cat foo.py | burn work review -
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

### 5. 落盘

```bash
burn --burn --preset code -n 50 -P 4 --save logs/burn.jsonl
# 每条调用结果会追加到 jsonl：{type, idx, model, text, usage, latency_ms}
```

### 6. 查模型

```bash
burn --models
# ✓ 12 个模型 @ https://model.hbscloud.com.cn/v1:
#   - gpt-4o  (openai)
#   - claude-3-5-sonnet  (anthropic)
#   ...
```

## 文件结构

```
claude-code-hbscloud/
├── burn/                  ← 主程序包
│   ├── __init__.py
│   ├── __main__.py        # python -m burn
│   ├── cli.py             # argparse
│   ├── client.py          # 同步 + 异步 + 流式 API 客户端
│   ├── tracker.py         # token / 成本 / 性能计数（线程安全）
│   ├── presets.py         # 5 种烧法
│   └── reporter.py        # 终端输出（流式 / 进度条 / 汇总）
├── bin/burn               # shell 包装
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
burn -p "..." \
  --model deepseek-reasoner \
  --temperature 0.2 \
  --max-tokens 4096
```

### 用作 Python 库

```python
from burn.client import HBSClient, ChatMessage

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
from burn.client import AsyncHBSClient, ChatMessage

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
**没有 Claude Code 也能用**——这正是 `burn` 的目的。

### Q: 怎么彻底切到 burn？
```bash
# 1. 编辑 .env
$EDITOR ~/claude-code-hbscloud/.env

# 2. 把 HBS_MODEL 设成你想要的模型
HBS_MODEL=deepseek-reasoner

# 3. 试一下
burn --models                  # 看看支持哪些模型
burn -p "hi" --max-tokens 16   # 试发一条
burn --burn --preset code -n 5 -P 2  # 烧 5 次
```

### Q: 想删掉旧 LiteLLM 文件
```bash
rm -rf ~/claude-code-hbscloud/legacy
```

### Q: 报 `[401] invalid api key`
去 hbscloud 控制台生成新 Key，编辑 `.env` 重试。

### Q: 报 SSL / 证书错误
一般是公司网络代理。设一下：
```bash
export HTTPS_PROXY=http://your-proxy:8080
```
或临时给 httpx 传 `proxies=...`。

---

## burn-review-tribunal (大型审判团) — *实施中*

对 burn 项目自身做 exhaustive 代码审查 + 烧 token 的 workflow 脚本（Node.js 实现，与上面 burn CLI 并列）。

详见：
- 设计: `docs/superpowers/specs/2026-06-06-burn-review-tribunal-design.md`
- 实施计划: `docs/superpowers/plans/2026-06-06-burn-review-tribunal.md`
- Skill: `.claude/skills/burn-review-tribunal/SKILL.md` *(Task 20 创建)*

```bash
# 跑
node .claude/workflows/burn-review-tribunal.js --target burn/   # *(Task 16-18 创建)*

# 测
npm test
```
