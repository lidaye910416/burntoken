# burntoken · Examples

> **自包含的、可直接跑的小 demo** —— 每个文件对应一种典型用法，
> 注释里都贴了 hbscloud 的真实回包样式，方便先看预期再决定跑不跑。

## 索引

| 文件 | 主题 | 命令 | 会发请求？ |
| --- | --- | --- | --- |
| [`00-version.sh`](00-version.sh) | 装好之后先跑：版本自检 | `./examples/00-version.sh` | 否 |
| [`01-single-call.sh`](01-single-call.sh) | 单条 prompt（最常用入口） | `./bin/burntoken -p "..."` | 是 |
| [`02-streaming.sh`](02-streaming.sh) | 流式输出（SSE） | `./bin/burntoken -p "..." --stream` | 是 |
| [`03-batch-burn.sh`](03-batch-burn.sh) | 批量烧 token + 熔断 + 落 jsonl | `./bin/burntoken burn --preset ...` | 是 |
| [`04-repl-session.txt`](04-repl-session.txt) | 交互 REPL 的真实记录（不需要跑） | `./bin/burntoken --repl` | 否（仅展示） |
| [`05-work-review.sh`](05-work-review.sh) | work 子任务：真干活（review / docs / tests …） | `./bin/burntoken work review <file>` | 是 |
| [`06-models-list.txt`](06-models-list.txt) | `--models` / `--providers` / `config show` 真实输出 | `./bin/burntoken --models` | 否（仅展示） |

## 怎么跑

```bash
# 1) 确保 .env 已填 HBS_API_KEY
cd ~/burntoken
[ -f .env ] || cp .env.example .env
$EDITOR .env

# 2) 直接跑某个 demo（脚本里会自己 cd 到项目根）
chmod +x examples/*.sh
./examples/01-single-call.sh
```

如果只想看命令、不真发请求：

```bash
./examples/03-batch-burn.sh demo   # 所有命令以注释形态打出来
```

## 读这些文件最快的姿势

- **新用户**：先看 [`04-repl-session.txt`](04-repl-session.txt) 感受交互流，
  再看 [`01-single-call.sh`](01-single-call.sh) 跑第一条。
- **要烧 token**：[`03-batch-burn.sh`](03-batch-burn.sh) 覆盖所有 preset + 熔断。
- **要真干活**：[`05-work-review.sh`](05-work-review.sh) 演示 work 8 种 task。
- **出错排错**：跑 [`06-models-list.txt`](06-models-list.txt) 里那几个命令，
  能验证 `.env` / `HBS_API_KEY` / `HBS_BASE_URL` 是不是通的。
- **流式体感**：[`02-streaming.sh`](02-streaming.sh) 里有 1 个 Python 直调示例，
  跳过 burntoken CLI 直接拿 stream iterator。

## 文件结构

```
examples/
├── README.md            ← 你正在看
├── 00-version.sh        ← 装好之后先跑：版本自检（不调 API）
├── 01-single-call.sh    ← run（默认命令）单条
├── 02-streaming.sh      ← --stream 流式
├── 03-batch-burn.sh     ← burn 子命令：N 次 / P 并发 / 熔断
├── 04-repl-session.txt  ← repl 子命令：交互示例
├── 05-work-review.sh    ← work 子任务：review / docs / tests / …
└── 06-models-list.txt   ← --models / --providers / config show
```

## 跟主 README 的关系

主 README 的「[用法](../../README.md#用法)」是按场景讲命令的；
本目录是按"跑一遍就懂"组织的。
两个文档互补：先读主 README 选命令，再来这里直接 `./examples/NN-xxx.sh` 看效果。
