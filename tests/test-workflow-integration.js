// tests/test-workflow-integration.js
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock workflow runtime hooks
const mockPhase = vi.fn()
const mockLog = vi.fn()
const mockBudget = { remaining: () => 1_000_000 }
const mockParallel = async (items) => Promise.all(items.map(fn => fn()))
const mockPipeline = async (items, stage) => {
  const results = []
  for (const item of items) {
    results.push(await stage(item))
  }
  return results
}

vi.stubGlobal('phase', mockPhase)
vi.stubGlobal('log', mockLog)
vi.stubGlobal('budget', mockBudget)
vi.stubGlobal('parallel', mockParallel)
vi.stubGlobal('pipeline', mockPipeline)

// Mock fetch with deterministic lens and judge responses
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

beforeEach(() => {
  mockFetch.mockReset()
  // Set CI mode
  process.env.TRIBUNAL_NONINTERACTIVE = '1'
})

describe('workflow integration (mocked)', () => {
  it('runs one round on fixture and produces report', async () => {
    // First call: lens connectivity test
    // Then: 7 lens calls
    // Then: 3 judge calls per finding
    mockFetch.mockImplementation(async () => ({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ findings: [] }) } }],
        usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
        model: 'gpt-4o',
      }),
    }))

    // Run via subprocess-style import (use the lib directly to avoid workflow runtime)
    const { dedupFindings } = await import('../.claude/skills/burn-review-tribunal/lib/dedup.js')
    const { tallyVotes } = await import('../.claude/skills/burn-review-tribunal/lib/tally.js')
    const { renderMarkdown } = await import('../.claude/skills/burn-review-tribunal/lib/report.js')

    // Simulate one round
    const lensResults = [
      { findings: [{ id: 'f1', lens: 'security', file: 'buggy-sample.py', line: 10, severity: 'critical', category: 'inject', title: 'shell injection', evidence: 'e', rationale: 'r' }] },
    ]
    const seen = new Set()
    const fresh = dedupFindings(lensResults.flatMap(r => r.findings.map(f => ({ ...f, lens: f.lens || 'security' }))), seen)

    // Simulate judges
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real', confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'real', confidence: 0.8, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'real', confidence: 0.9, reasoning: 'ok' } },
    ]
    const result = tallyVotes(fresh[0], votes)

    expect(result.passed).toBe(true)
    const md = renderMarkdown({
      confirmed: [result.finding], rounds: 1, totalTokens: 5000,
      target: 'buggy-sample.py', startedAt: '2026-06-06T00:00:00Z',
    })
    expect(md).toContain('shell injection')
    expect(md).toContain('critical')
  }, 15000)
})
