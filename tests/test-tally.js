// tests/test-tally.js
import { describe, it, expect } from 'vitest'
import { tallyVotes } from '../.claude/skills/burn-review-tribunal/lib/tally.js'

const f = { id: 'f1', file: 'a.py', line: 10, category: 'state', title: 'x' }

describe('tallyVotes', () => {
  it('passes when 2/3 judges say real and isSignificant is confident', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real',    confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'real',    confidence: 0.7, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'real',    confidence: 0.8, reasoning: 'ok' } },
    ]
    expect(tallyVotes(f, votes).passed).toBe(true)
  })

  it('fails when only 1/3 judges say real', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real',     confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'refuted',  confidence: 0.9, reasoning: 'no' } },
      { lens: 'isActionable',  verdict: { verdict: 'refuted',  confidence: 0.9, reasoning: 'no' } },
    ]
    expect(tallyVotes(f, votes).passed).toBe(false)
  })

  it('fails when isReal is refuted even with 2/3 majority', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'refuted', confidence: 0.9, reasoning: 'no' } },
      { lens: 'isSignificant', verdict: { verdict: 'real',    confidence: 0.7, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'real',    confidence: 0.8, reasoning: 'ok' } },
    ]
    expect(tallyVotes(f, votes).passed).toBe(false)
  })

  it('fails when isSignificant confidence < 0.6', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real', confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'real', confidence: 0.4, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'real', confidence: 0.8, reasoning: 'ok' } },
    ]
    expect(tallyVotes(f, votes).passed).toBe(false)
  })

  it('fails when isActionable is refuted', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real',    confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'real',    confidence: 0.7, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'refuted', confidence: 0.9, reasoning: 'no' } },
    ]
    expect(tallyVotes(f, votes).passed).toBe(false)
  })

  it('attaches votes to result', () => {
    const votes = [
      { lens: 'isReal',        verdict: { verdict: 'real', confidence: 0.9, reasoning: 'ok' } },
      { lens: 'isSignificant', verdict: { verdict: 'real', confidence: 0.7, reasoning: 'ok' } },
      { lens: 'isActionable',  verdict: { verdict: 'real', confidence: 0.8, reasoning: 'ok' } },
    ]
    const result = tallyVotes(f, votes)
    expect(result.votes).toBeDefined()
    expect(result.votes.isReal.verdict).toBe('real')
  })
})
