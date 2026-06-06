// tests/test-config.js
import { describe, it, expect } from 'vitest'
import { expandEnv, loadProvidersFile, resolvePreset } from '../.claude/skills/burn-review-tribunal/lib/config.js'

describe('expandEnv', () => {
  it('replaces ${VAR} with env value', () => {
    process.env.TEST_KEY = 'sk-xyz'
    expect(expandEnv('${TEST_KEY}')).toBe('sk-xyz')
    delete process.env.TEST_KEY
  })

  it('returns empty string for unset var', () => {
    delete process.env.UNSET_VAR_X
    expect(expandEnv('${UNSET_VAR_X}')).toBe('')
  })
})

describe('loadProvidersFile', () => {
  it('returns null for missing file', () => {
    expect(loadProvidersFile('/nonexistent/path.json')).toBe(null)
  })

  it('expands env placeholders in keys', () => {
    process.env.PROVIDER_KEY_TEST = 'sk-real'
    const fs = require('fs')
    const tmp = '/tmp/test-providers.json'
    fs.writeFileSync(tmp, JSON.stringify({
      providers: {
        test: { type: 'openai', endpoint: 'https://x.com/v1', key: '${PROVIDER_KEY_TEST}' },
      },
    }))
    const data = loadProvidersFile(tmp)
    expect(data.providers.test.key).toBe('sk-real')
    fs.unlinkSync(tmp)
    delete process.env.PROVIDER_KEY_TEST
  })
})

describe('resolvePreset', () => {
  it('returns preset config', () => {
    const cfg = {
      presets: { balanced: { lens: { provider: 'hbscloud', model: 'x' }, judge: { provider: 'openai', model: 'y' } } },
    }
    const p = resolvePreset(cfg, 'balanced')
    expect(p.lens.provider).toBe('hbscloud')
  })

  it('returns null for unknown preset', () => {
    expect(resolvePreset({ presets: {} }, 'nope')).toBe(null)
  })
})
