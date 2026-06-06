---
name: burn-review-tribunal
description: Use when user invokes "burn tribunal" or "code review tribunal" or wants to do exhaustive multi-lens code review while consuming hbscloud/OpenAI/Anthropic API tokens. Triggers a multi-round scan with 7 lens perspectives and 3 adversarial judges.
---

# burn 审判团

大型审判团式代码审查 + Token 燃烧 workflow 脚本。

详见 `docs/superpowers/specs/2026-06-06-burn-review-tribunal-design.md`。

## 快速开始

```bash
# 1. 在项目中放一个 workflow 入口
# .claude/workflows/burn-review-tribunal.js  ← 已就绪

# 2. 引导式配置模型（首次）
# 跟随提示填入 provider/endpoint/key/model

# 3. 跑
node .claude/workflows/burn-review-tribunal.js --target burn/

# 4. 看报告
ls reviews/tribunal_*.md
```

## CLI 速查

| Flag | 默认值 | 说明 |
|------|--------|------|
| `--max-rounds <n>` | 10 | 硬上限轮数 |
| `--dry-threshold <n>` | 2 | 连续 N 轮无新发现才退出 |
| `--token-budget <k>` | 300 | 累计 token 预算（k tokens） |
| `--lens <list>` | 全部 7 个 | 只跑指定的 lens（逗号分隔） |
| `--interactive` | yes | 每轮结束询问是否继续 |
| `--dry-run` | no | 只跑 1 个 lens 验证连通性 |
| `--target <glob>` | burn/ | 审查目标路径 |
| `--out-dir <path>` | reviews/ | 报告输出目录 |
| `--preset <name>` | - | 沿用 providers.json 中的预设 |

## 预设示例

```json
{
  "presets": {
    "balanced": { "lens":  { "provider": "hbscloud", "model": "deepseek-reasoner" },
                  "judge": { "provider": "openai",   "model": "gpt-4o" } }
  }
}
```

## 工作原理

1. **Setup**: 解析参数、加载校准、引导式填模型、连通性测试
2. **Scan**: 7 lens 并行扫一轮（每轮 ~14k tokens）
3. **Verify**: 3 judge 对每个新发现做 adversarial 验证（倾向 refute）
4. **Loop**: 去重 vs seen、累计 confirmed、判断 dry count
5. **Report**: 退出时输出 markdown + JSON

退出条件（满足任一即停）：
- 连续 2 轮无新发现
- 达到 max-rounds
- token 预算耗尽
- 用户中断

## 配置文件

`~/.config/burn-tribunal/providers.json`：

```json
{
  "providers": {
    "hbscloud": {
      "type": "openai",
      "endpoint": "https://model.hbscloud.com.cn/v1",
      "key": "${HBS_API_KEY}"
    }
  },
  "presets": { /* ... */ }
}
```

## 开发

```bash
npm test                       # 全部测试
npm test -- tests/test-dedup   # 单个文件
```
