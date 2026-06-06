// .claude/skills/burn-review-tribunal/lib/cli.js
import yargs from 'yargs'
import { hideBin } from 'yargs/helpers'

/**
 * Parse command-line arguments into a config object.
 *
 * Accepts either a clean argv list (e.g. ['--max-rounds', '5']) or
 * the full process.argv (with node + script as first two entries).
 */
export function parseArgs(argv) {
  // Detect process.argv style (first entry looks like an executable path)
  // and strip the leading two entries with hideBin. Otherwise treat as
  // already-clean argv.
  const looksLikeProcessArgv =
    Array.isArray(argv) &&
    argv.length >= 2 &&
    typeof argv[0] === 'string' &&
    !argv[0].startsWith('-')
  const args = looksLikeProcessArgv ? hideBin(argv) : argv
  const parser = yargs(args)
    .option('max-rounds', {
      type: 'number', default: 10,
      describe: 'Hard cap on number of scan rounds',
    })
    .option('dry-threshold', {
      type: 'number', default: 2,
      describe: 'Consecutive rounds with no new findings before exit',
    })
    .option('token-budget', {
      type: 'number', default: 300,
      describe: 'Token budget in thousands (e.g. 300 = 300k)',
    })
    .option('lens', {
      type: 'string', default: '',
      describe: 'Comma-separated lens list (default: all 7)',
    })
    .option('interactive', {
      type: 'boolean', default: true,
      describe: 'Pause between rounds for user confirmation',
    })
    .option('dry-run', {
      type: 'boolean', default: false,
      describe: 'Run 1 cheap lens to verify connectivity, then exit',
    })
    .option('target', {
      type: 'string', default: 'burn/',
      describe: 'File glob or directory to review',
    })
    .option('out-dir', {
      type: 'string', default: 'reviews/',
      describe: 'Output directory for reports',
    })
    .option('preset', {
      type: 'string', default: '',
      describe: 'Use a named preset from providers.json',
    })
    .option('save-config', {
      type: 'boolean', default: false,
      describe: 'Save provider config to ~/.config/burn-tribunal/providers.json',
    })
    .help()

  const raw = parser.parse()
  return {
    maxRounds: raw['max-rounds'],
    dryThreshold: raw['dry-threshold'],
    tokenBudget: raw['token-budget'],
    lens: raw.lens ? raw.lens.split(',').map(s => s.trim()) : null,
    interactive: raw.interactive,
    dryRun: raw['dry-run'],
    target: raw.target,
    outDir: raw['out-dir'],
    preset: raw.preset || null,
    saveConfig: raw['save-config'],
  }
}

/**
 * Build the list of interactive prompt questions for a model role.
 *
 * @param {'lens' | 'judge'} role
 * @returns {Array<{name: string, message: string, default?: any}>}
 */
export function buildPromptQuestions(role) {
  const label = role === 'lens' ? 'lens 模型' : 'judge 模型'
  return [
    { name: 'provider', message: `${label} - 提供方 (hbscloud/openai/anthropic/custom):` },
    { name: 'endpoint', message: `${label} - 端点 (回车用默认):` },
    { name: 'key',      message: `${label} - API Key:`, type: 'password' },
    { name: 'model',    message: `${label} - 模型名:` },
  ]
}
