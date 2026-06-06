// tests/test-cli.js
import { describe, it, expect } from 'vitest'
import { parseArgs, buildPromptQuestions } from '../.claude/skills/burn-review-tribunal/lib/cli.js'

describe('parseArgs', () => {
  it('returns defaults when no args', () => {
    const cfg = parseArgs([])
    expect(cfg.maxRounds).toBe(10)
    expect(cfg.dryThreshold).toBe(2)
    expect(cfg.tokenBudget).toBe(300)
    expect(cfg.interactive).toBe(true)
    expect(cfg.dryRun).toBe(false)
  })

  it('overrides via flags', () => {
    const cfg = parseArgs(['--max-rounds', '5', '--token-budget', '100', '--no-interactive'])
    expect(cfg.maxRounds).toBe(5)
    expect(cfg.tokenBudget).toBe(100)
    expect(cfg.interactive).toBe(false)
  })

  it('parses --lens list', () => {
    const cfg = parseArgs(['--lens', 'correctness,security'])
    expect(cfg.lens).toEqual(['correctness', 'security'])
  })

  it('parses --preset', () => {
    const cfg = parseArgs(['--preset', 'balanced'])
    expect(cfg.preset).toBe('balanced')
  })

  it('--dry-run sets dryRun=true', () => {
    expect(parseArgs(['--dry-run']).dryRun).toBe(true)
  })
})

describe('buildPromptQuestions', () => {
  it('returns question list for lens config', () => {
    const qs = buildPromptQuestions('lens')
    expect(qs.length).toBeGreaterThanOrEqual(4)
    expect(qs.some(q => q.name === 'provider')).toBe(true)
    expect(qs.some(q => q.name === 'key')).toBe(true)
    expect(qs.some(q => q.name === 'model')).toBe(true)
  })
})
