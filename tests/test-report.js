// tests/test-report.js
import { describe, it, expect } from 'vitest'
import { renderMarkdown, renderJson, groupByFile } from '../.claude/skills/burn-review-tribunal/lib/report.js'

const sample = [
  { id: 'f1', lens: 'correctness', file: 'burn/client.py', line: 142, severity: 'critical',
    category: 'state', title: 'Stream leak on timeout', evidence: 'code', rationale: 'r',
    votes: { isReal: { verdict: 'real', confidence: 0.9, reasoning: 'ok' } } },
  { id: 'f2', lens: 'security', file: 'burn/cli.py', line: 50, severity: 'major',
    category: 'inject', title: 'Shell injection', evidence: 'code', rationale: 'r',
    votes: {} },
]

describe('groupByFile', () => {
  it('groups findings by file', () => {
    const g = groupByFile(sample)
    expect(Object.keys(g).sort()).toEqual(['burn/cli.py', 'burn/client.py'])
    expect(g['burn/client.py']).toHaveLength(1)
  })
})

describe('renderMarkdown', () => {
  it('includes title and summary', () => {
    const md = renderMarkdown({
      confirmed: sample, rounds: 5, totalTokens: 187432,
      target: 'burn/', startedAt: '2026-06-06T14:23:00+08:00',
    })
    expect(md).toContain('# burn 审判团')
    expect(md).toContain('client.py')
    expect(md).toContain('critical')
    expect(md).toContain('Stream leak')
  })
})

describe('renderJson', () => {
  it('produces a complete JSON object', () => {
    const obj = renderJson({
      confirmed: sample, rounds: 5, totalTokens: 187432,
      target: 'burn/', startedAt: '2026-06-06T14:23:00+08:00',
    })
    expect(obj.workflow).toBe('burn-review-tribunal')
    expect(obj.confirmed_count).toBe(2)
    expect(obj.findings).toHaveLength(2)
    expect(obj.by_severity.critical).toBe(1)
    expect(obj.by_severity.major).toBe(1)
  })
})
