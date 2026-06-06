// tests/test-pricing.js
import { describe, it, expect } from 'vitest'
import { BUILTIN_PRICING, computeCost } from '../.claude/skills/burn-review-tribunal/lib/pricing.js'

describe('BUILTIN_PRICING', () => {
  it('includes common models', () => {
    expect(BUILTIN_PRICING['gpt-4o']).toBeDefined()
    expect(BUILTIN_PRICING['deepseek-reasoner']).toBeDefined()
  })

  it('has prompt and completion rates per 1k tokens', () => {
    const p = BUILTIN_PRICING['gpt-4o']
    expect(p.prompt).toBeGreaterThan(0)
    expect(p.completion).toBeGreaterThan(0)
  })
})

describe('computeCost', () => {
  it('computes cost for given usage', () => {
    // gpt-4o: prompt 0.005, completion 0.015 per 1k
    const cost = computeCost('gpt-4o', { prompt_tokens: 1000, completion_tokens: 1000 })
    // 1 * 0.005 + 1 * 0.015 = 0.02
    expect(cost).toBeCloseTo(0.02, 5)
  })

  it('returns null for unknown model', () => {
    expect(computeCost('unknown-model', { prompt_tokens: 100, completion_tokens: 100 })).toBe(null)
  })
})
