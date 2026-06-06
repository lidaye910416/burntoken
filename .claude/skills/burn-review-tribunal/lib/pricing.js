// .claude/skills/burn-review-tribunal/lib/pricing.js

// Prices per 1k tokens. Currency: USD unless noted.
export const BUILTIN_PRICING = {
  'gpt-4o':            { prompt: 0.005,   completion: 0.015,   currency: 'USD' },
  'gpt-4o-mini':       { prompt: 0.00015, completion: 0.0006,  currency: 'USD' },
  'gpt-3.5-turbo':     { prompt: 0.0005,  completion: 0.0015,  currency: 'USD' },
  'deepseek-reasoner': { prompt: 0.001,   completion: 0.002,   currency: 'CNY' },
  'claude-3-5-sonnet': { prompt: 0.003,   completion: 0.015,   currency: 'USD' },
  'claude-3-haiku':    { prompt: 0.00025, completion: 0.00125, currency: 'USD' },
}

/**
 * Compute cost for a single model call.
 *
 * @param {string} modelName
 * @param {{prompt_tokens: number, completion_tokens: number}} usage
 * @returns {number|null} cost in pricing currency, or null if model unknown
 */
export function computeCost(modelName, usage) {
  const rate = BUILTIN_PRICING[modelName]
  if (!rate) return null
  const p = (usage.prompt_tokens || 0) / 1000 * rate.prompt
  const c = (usage.completion_tokens || 0) / 1000 * rate.completion
  return p + c
}
