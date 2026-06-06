import { describe, it, expect } from 'vitest'
import Ajv from 'ajv'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')

const ajv = new Ajv({ allErrors: true })

const findingSchema = JSON.parse(readFileSync(join(ROOT, '.claude/skills/burn-review-tribunal/schemas/finding.json'), 'utf8'))
const verdictSchema = JSON.parse(readFileSync(join(ROOT, '.claude/skills/burn-review-tribunal/schemas/verdict.json'), 'utf8'))

const validateFinding = ajv.compile(findingSchema)
const validateVerdict = ajv.compile(verdictSchema)

describe('finding schema', () => {
  it('accepts a valid finding', () => {
    const data = {
      findings: [{
        id: 'f_abc',
        lens: 'correctness',
        file: 'burn/client.py',
        line: 142,
        severity: 'critical',
        category: 'state',
        title: 'AsyncHBSClient timeout 后未取消 stream',
        evidence: 'code snippet',
        rationale: 'why it is a problem',
      }],
    }
    expect(validateFinding(data)).toBe(true)
  })

  it('rejects missing required fields', () => {
    const data = { findings: [{ id: 'f_abc' }] }
    expect(validateFinding(data)).toBe(false)
  })

  it('rejects invalid lens enum', () => {
    const data = {
      findings: [{
        id: 'f_abc', lens: 'wrong', file: 'a.py', line: 1,
        severity: 'major', category: 'x', title: 't', evidence: 'e', rationale: 'r',
      }],
    }
    expect(validateFinding(data)).toBe(false)
  })
})

describe('verdict schema', () => {
  it('accepts a valid verdict', () => {
    expect(validateVerdict({ verdict: 'real', confidence: 0.9, reasoning: 'ok' })).toBe(true)
  })

  it('rejects confidence out of range', () => {
    expect(validateVerdict({ verdict: 'real', confidence: 1.5, reasoning: 'ok' })).toBe(false)
  })
})
