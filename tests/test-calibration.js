// tests/test-calibration.js
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  loadCalibration,
  saveCalibration,
  recordSample,
  getAvgTokens,
} from '../.claude/skills/burn-review-tribunal/lib/calibration.js'

let tmpDir
beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'calib-'))
})
afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})

describe('loadCalibration / saveCalibration', () => {
  it('returns default when file does not exist', () => {
    const data = loadCalibration(tmpDir)
    expect(data.lens).toEqual({})
    expect(data.judge).toEqual({})
  })

  it('round-trips data', () => {
    const data = {
      lens: { correctness: { avg_output_tokens: 2150, samples: 12 } },
      judge: { isReal: { avg_output_tokens: 480, samples: 47 } },
      last_updated: '2026-06-06T00:00:00Z',
    }
    saveCalibration(tmpDir, data)
    const loaded = loadCalibration(tmpDir)
    expect(loaded.lens.correctness.avg_output_tokens).toBe(2150)
  })
})

describe('recordSample', () => {
  it('updates running average', () => {
    const data = { lens: {}, judge: {} }
    recordSample(data, 'lens', 'correctness', 2000)
    recordSample(data, 'lens', 'correctness', 3000)
    expect(data.lens.correctness.avg_output_tokens).toBe(2500)
    expect(data.lens.correctness.samples).toBe(2)
  })

  it('preserves other lens entries', () => {
    const data = { lens: { security: { avg_output_tokens: 1000, samples: 1 } }, judge: {} }
    recordSample(data, 'lens', 'correctness', 2000)
    expect(data.lens.security.avg_output_tokens).toBe(1000)
  })
})

describe('getAvgTokens', () => {
  it('returns 0 when no samples', () => {
    const data = { lens: {}, judge: {} }
    expect(getAvgTokens(data, 'lens', 'correctness')).toBe(0)
  })

  it('returns avg when samples exist', () => {
    const data = {
      lens: { correctness: { avg_output_tokens: 2000, samples: 5 } },
      judge: {},
    }
    expect(getAvgTokens(data, 'lens', 'correctness')).toBe(2000)
  })
})
