// .claude/skills/burn-review-tribunal/lib/prompts.js
import { createInterface } from 'readline/promises'
import { stdin as input, stdout as output } from 'process'

const PROVIDER_PRESETS = {
  hbscloud:  { type: 'openai', endpoint: 'https://model.hbscloud.com.cn/v1', defaultModel: 'deepseek-reasoner' },
  openai:    { type: 'openai', endpoint: 'https://api.openai.com/v1',          defaultModel: 'gpt-4o' },
  anthropic: { type: 'anthropic', endpoint: 'https://api.anthropic.com',       defaultModel: 'claude-3-5-sonnet-20241022' },
}

function maskKey(key) {
  if (!key) return '(empty)'
  if (key.length <= 8) return '***'
  return key.slice(0, 4) + '...' + key.slice(-4)
}

/**
 * Prompt the user once for a single field.
 * Falls back to default when empty input.
 */
async function promptOnce(rl, message, defaultValue = '', { silent = false } = {}) {
  const display = defaultValue ? `${message} [${silent ? '***' : defaultValue}]: ` : `${message}: `
  const answer = (await rl.question(display)).trim()
  return answer || defaultValue
}

/**
 * Interactively collect model configuration from the user.
 *
 * @param {'lens' | 'judge'} role
 * @param {object|null} existing - existing config to skip questions
 * @returns {Promise<{provider: string, type: string, endpoint: string, key: string, model: string}>}
 */
export async function promptModelConfig(role, existing = null) {
  const rl = createInterface({ input, output })

  try {
    const label = role === 'lens' ? 'lens' : 'judge'

    if (existing) {
      console.log(`\n${label} (沿用): provider=${existing.provider} model=${existing.model} key=${maskKey(existing.key)}`)
      return existing
    }

    const provider = await promptOnce(rl, `${label} 提供方 (hbscloud/openai/anthropic/custom)`)
    const preset = PROVIDER_PRESETS[provider] ?? PROVIDER_PRESETS.hbscloud

    const endpoint = await promptOnce(rl, `${label} 端点`, preset.endpoint)
    const type = provider === 'anthropic' ? 'anthropic' : (provider === 'custom' ? 'openai' : preset.type)

    const key = await promptOnce(rl, `${label} API Key (输入隐藏)`, '', { silent: true })
    const model = await promptOnce(rl, `${label} 模型名`, preset.defaultModel)

    return { provider, type, endpoint, key, model }
  } finally {
    rl.close()
  }
}

/**
 * Ask the user a yes/no question.
 * @returns {Promise<boolean>}
 */
export async function promptYesNo(question, defaultYes = true) {
  const rl = createInterface({ input, output })
  try {
    const suffix = defaultYes ? ' [Y/n]:' : ' [y/N]:'
    const answer = (await rl.question(`${question}${suffix} `)).trim().toLowerCase()
    if (!answer) return defaultYes
    return answer === 'y' || answer === 'yes'
  } finally {
    rl.close()
  }
}
