// tests/test-dedup.js
import { describe, it, expect } from 'vitest'
import { dedupKey, dedupFindings, normalizePath } from '../.claude/skills/burn-review-tribunal/lib/dedup.js'

describe('normalizePath', () => {
  it('strips leading ./', () => {
    expect(normalizePath('./burn/client.py')).toBe('burn/client.py')
  })

  it('normalizes backslashes to forward', () => {
    expect(normalizePath('burn\\client.py')).toBe('burn/client.py')
  })

  it('lowercases the path', () => {
    expect(normalizePath('Burn/Client.py')).toBe('burn/client.py')
  })
})

describe('dedupKey', () => {
  it('groups same file+line+category', () => {
    const a = { file: 'burn/client.py', line: 142, category: 'state' }
    const b = { file: 'burn/client.py', line: 142, category: 'state' }
    expect(dedupKey(a)).toBe(dedupKey(b))
  })

  it('groups lines within 3-line bucket', () => {
    const a = { file: 'burn/client.py', line: 142, category: 'state' }
    const b = { file: 'burn/client.py', line: 144, category: 'state' }
    expect(dedupKey(a)).toBe(dedupKey(b))
  })

  it('separates different files', () => {
    const a = { file: 'burn/client.py', line: 142, category: 'state' }
    const b = { file: 'burn/cli.py', line: 142, category: 'state' }
    expect(dedupKey(a)).not.toBe(dedupKey(b))
  })

  it('separates different categories', () => {
    const a = { file: 'burn/client.py', line: 142, category: 'state' }
    const b = { file: 'burn/client.py', line: 142, category: 'logic' }
    expect(dedupKey(a)).not.toBe(dedupKey(b))
  })
})

describe('dedupFindings', () => {
  it('removes duplicates from a single round', () => {
    const findings = [
      { id: 'f1', file: 'a.py', line: 10, category: 'state', title: 'x' },
      { id: 'f2', file: 'a.py', line: 11, category: 'state', title: 'y' }, // dup of f1
      { id: 'f3', file: 'b.py', line: 5, category: 'logic', title: 'z' },
    ]
    const result = dedupFindings(findings, new Set())
    expect(result).toHaveLength(2)
    expect(result.map(f => f.id)).toEqual(['f1', 'f3'])
  })

  it('respects seen set from previous rounds', () => {
    const seen = new Set(['burn/client.py|15|state'])
    const findings = [
      { id: 'f1', file: 'burn/client.py', line: 48, category: 'state', title: 'x' },
    ]
    const result = dedupFindings(findings, seen)
    expect(result).toHaveLength(0)
  })

  it('adds fresh findings to seen', () => {
    const seen = new Set()
    dedupFindings([{ id: 'f1', file: 'a.py', line: 10, category: 'x', title: 't' }], seen)
    expect(seen.size).toBe(1)
  })
})
