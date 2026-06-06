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
}

run().catch(err => {
  console.error('Workflow failed:', err)
  process.exit(1)
})
