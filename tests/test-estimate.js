// tests/test-estimate.js
import { describe, it, expect } from 'vitest'
import { estimateRoundCost, buildMatrix, formatMatrix } from '../.claude/skills/burn-review-tribunal/lib/estimate.js'

describe('estimateRoundCost', () => {
  it('computes lens + judge cost', () => {
    const data = {
      lens: { correctness: { avg_output_tokens: 2000, samples: 5 } },
      judge: { isReal: { avg_output_tokens: 500, samples: 10 } },
    }
    const cfg = { lens: ['correctness'], judge: ['isReal'], lensCount: 1, judgePerFinding: 1 }
    // 1 lens * 2000 + 1 finding * 1 judge * 500 = 2500
    expect(estimateRoundCost(data, cfg, 1)).toBe(2500)
  })

  it('uses defaults when calibration is empty', () => {
    const data = { lens: {}, judge: {} }
    const cfg = { lens: ['correctness', 'security'], judge: ['isReal', 'isSignificant', 'isActionable'], lensCount: 2, judgePerFinding: 3 }
    // defaults: 2000 per lens, 500 per judge
    // 2 * 2000 + F * 3 * 500 = 4000 + 1500 * F
    expect(estimateRoundCost(data, cfg, 0)).toBe(4000)
    expect(estimateRoundCost(data, cfg, 10)).toBe(19000)
  })
})

describe('buildMatrix', () => {
  it('builds 4x3 matrix of total tokens', () => {
    const cfg = { lens: ['a'], judge: ['b'], lensCount: 1, judgePerFinding: 1 }
    const data = { lens: {}, judge: {} }
    const matrix = buildMatrix(data, cfg, [3, 5, 7, 10], [5, 10, 20])
    expect(matrix).toHaveLength(4)
    expect(matrix[0]).toHaveLength(3)
    // row 0 (3 rounds), col 0 (F=5)
    // 3 * (1*2000 + 5*1*500) = 3 * 4500 = 13500
    expect(matrix[0][0]).toBe(13500)
  })
})

describe('formatMatrix', () => {
  it('renders ASCII table', () => {
    const matrix = [[100, 200], [300, 400]]
    const out = formatMatrix(matrix, [1, 2], [5, 10])
    expect(out).toContain('5')
    expect(out).toContain('10')
    expect(out).toContain('100')
    expect(out).toContain('400')
  })
})
