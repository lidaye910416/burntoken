// .claude/workflows/burn-review-tribunal.js
import { parseArgs } from '../skills/burn-review-tribunal/lib/cli.js'
import { loadCalibration } from '../skills/burn-review-tribunal/lib/calibration.js'
import { buildMatrix, formatMatrix, estimateRoundCost } from '../skills/burn-review-tribunal/lib/estimate.js'
import { renderMarkdown, renderJson } from '../skills/burn-review-tribunal/lib/report.js'
import { OpenAIProvider } from '../skills/burn-review-tribunal/lib/providers/openai.js'
import { AnthropicProvider } from '../skills/burn-review-tribunal/lib/providers/anthropic.js'
import { dedupFindings, dedupKey } from '../skills/burn-review-tribunal/lib/dedup.js'
import { tallyVotes } from '../skills/burn-review-tribunal/lib/tally.js'
import { promptModelConfig, promptYesNo } from '../skills/burn-review-tribunal/lib/prompts.js'
import { readFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SKILL_DIR = join(__dirname, '../skills/burn-review-tribunal')

export const meta = {
  name: 'burn-review-tribunal',
  description: '大型审判团代码审查 + Token 燃烧（多轮循环到枯竭）',
  phases: [
    { title: 'Setup' },
    { title: 'Scan' },
    { title: 'Verify' },
    { title: 'Loop' },
    { title: 'Report' },
  ],
}

const ALL_LENSES = ['correctness', 'security', 'performance', 'style', 'api', 'testability', 'docs']
const ALL_JUDGES = ['isReal', 'isSignificant', 'isActionable']
const ROUND_LIST = [3, 5, 7, 10]
const FINDING_LIST = [5, 10, 20]

function loadPrompt(lensName) {
  return readFileSync(join(SKILL_DIR, 'prompts', `lens-${lensName}.md`), 'utf8')
}

function buildLensConfig(provider) {
  return {
    messages: (target) => [
      { role: 'system', content: '你是 burn 项目的资深代码审查师。' },
      { role: 'user',   content: `${loadPrompt()}\n\n扫描目标：${target}` },
    ],
    model: provider.model,
    max_tokens: 4096,
    temperature: 0.2,
  }
}

// ... (continued in next tasks)
export default async function run() {
  const args = parseArgs(process.argv.slice(2))
  phase('Setup')

  const lensNames = args.lens ?? ALL_LENSES
  log(`Lens pool (${lensNames.length}): ${lensNames.join(', ')}`)
  log(`Max rounds: ${args.maxRounds}, dry threshold: ${args.dryThreshold}`)
  log(`Token budget: ${(args.tokenBudget / 1000).toFixed(0)}k`)

  const calibDir = process.env.TRIBUNAL_CALIB_DIR || join(process.env.HOME || '~', '.cache/burn-tribunal')
  const calib = loadCalibration(calibDir)
  const cfg = { lens: lensNames, judge: ALL_JUDGES, lensCount: lensNames.length, judgePerFinding: ALL_JUDGES.length }
  const matrix = buildMatrix(calib, cfg, ROUND_LIST, FINDING_LIST)

  log('── 预估 ──')
  log(formatMatrix(matrix, ROUND_LIST, FINDING_LIST))

  // Interactive: ask for model config
  log('── 配置模型 ──')
  const lensCfg = await promptModelConfig('lens')
  const judgeCfg = args.preset && (await promptYesNo('judge 沿用 lens 配置?', true))
    ? lensCfg
    : await promptModelConfig('judge')

  // Build provider instances
  function makeProvider(cfg) {
    if (cfg.type === 'anthropic') return new AnthropicProvider(cfg)
    return new OpenAIProvider(cfg)
  }
  const lensProvider = makeProvider(lensCfg)
  const judgeProvider = makeProvider(judgeCfg)

  log(`✓ lens: ${lensCfg.provider}/${lensCfg.model}`)
  log(`✓ judge: ${judgeCfg.provider}/${judgeCfg.model}`)

  // Test connectivity with one cheap call
  log('── 连通性测试 ──')
  try {
    const r = await lensProvider.chat(
      [{ role: 'user', content: 'ping' }],
      { model: lensCfg.model, max_tokens: 8 }
    )
    log(`✓ lens OK: ${r.usage.total_tokens} tokens, ${r.latency_ms}ms`)
  } catch (err) {
    log(`✗ lens 失败: ${err.message}`)
    throw err
  }


  // ── Main loop ──
  const confirmed = []
  const seen = new Set()
  let dry = 0
  let round = 0
  const totalSpent = { tokens: 0, calls: 0 }
  const target = args.target
  const FINDING_SCHEMA = { type: 'object', properties: { findings: { type: 'array' } } }
  const VERDICT_SCHEMA = { type: 'object', properties: { verdict: { type: 'string' }, confidence: { type: 'number' }, reasoning: { type: 'string' } } }

  while (dry < args.dryThreshold && round < args.maxRounds && budget.remaining() > 50_000) {
    round++
    phase('Scan')
    log(`── Round ${round} ──`)

    // 7 lens 并行扫
    const lensResults = await pipeline(
      lensNames,
      async (lensName) => {
        const prompt = loadPrompt(lensName).replace('{target}', target)
        const r = await lensProvider.chat(
          [
            { role: 'system', content: '你是 burn 项目的资深代码审查师。' },
            { role: 'user', content: prompt },
          ],
          { model: lensCfg.model, max_tokens: 4096, temperature: 0.2, response_format: { type: 'json_object' } }
        )
        totalSpent.tokens += r.usage.total_tokens
        totalSpent.calls += 1
        try {
          const parsed = JSON.parse(r.text)
          return (parsed.findings ?? []).map(f => ({ ...f, lens: lensName }))
        } catch {
          log(`  ⚠ ${lensName} 解析失败`)
          return []
        }
      }
    )

    const raw = lensResults.flat()
    const fresh = dedupFindings(raw, seen)

    if (fresh.length === 0) {
      dry++
      log(`  Round ${round}: 0 新发现 (dry=${dry})`)
      continue
    }
    dry = 0

    phase('Verify')
    log(`  ${fresh.length} 个新发现, 启动 ${fresh.length * 3} 个 judge...`)

    const verified = await parallel(fresh.map(f => async () => {
      const votes = await parallel(ALL_JUDGES.map(j => async () => {
        const judgePrompt = `你是 adversarial 验证师，倾向于 refute。\n\n验证 finding: ${JSON.stringify(f)}\n\n视角: ${j}\n规则: ${j === 'isReal' ? '这是真实问题还是幻觉/过度解读？' : j === 'isSignificant' ? '严重程度是否值得记录？(confidence >= 0.6)' : '能否给出 ≤ 5 行的具体修复？'}\n\n返回 JSON: { "verdict": "real|refuted", "confidence": 0.0-1.0, "reasoning": "..." }`
        try {
          const r = await judgeProvider.chat(
            [{ role: 'user', content: judgePrompt }],
            { model: judgeCfg.model, max_tokens: 500, temperature: 0.1, response_format: { type: 'json_object' } }
          )
          totalSpent.tokens += r.usage.total_tokens
          totalSpent.calls += 1
          const verdict = JSON.parse(r.text)
          return { lens: j, verdict }
        } catch (err) {
          log(`    ⚠ judge ${j} 失败: ${err.message}`)
          return { lens: j, verdict: { verdict: 'refuted', confidence: 0, reasoning: 'judge error' } }
        }
      }))
      return tallyVotes(f, votes)
    }))

    const passed = verified.filter(v => v.passed)
    confirmed.push(...passed.map(v => ({ ...v.finding, votes: v.votes })))

    log(`  Round ${round}: +${fresh.length} new, +${passed.length} confirmed`)

    phase('Loop')
    log(`  累计: ${confirmed.length} confirmed, ~${(totalSpent.tokens / 1000).toFixed(0)}k tokens`)

    if (args.interactive && round < args.maxRounds) {
      const cont = await promptYesNo(`继续下一轮？ (y/n)`, true)
      if (!cont) {
        log('  用户中断')
        break
      }
    }
  }

  phase('Report')
  const startedAt = new Date().toISOString()
  const markdown = renderMarkdown({
    confirmed, rounds: round, totalTokens: totalSpent.tokens,
    target, startedAt,
  })
  const json = renderJson({
    confirmed, rounds: round, totalTokens: totalSpent.tokens,
    target, startedAt,
  })

  log('── 报告 ──')
  log(markdown)
  log(`\nJSON: ${JSON.stringify(json, null, 2)}`)

  return { confirmed, rounds: round, totalTokens: totalSpent.tokens }
}

run().catch(err => {
  console.error('Workflow failed:', err)
  process.exit(1)
})
