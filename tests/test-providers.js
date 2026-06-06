// tests/test-providers.js
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

const { OpenAIProvider } = await import('../.claude/skills/burn-review-tribunal/lib/providers/openai.js')

beforeEach(() => {
  mockFetch.mockReset()
})

describe('OpenAIProvider', () => {
  it('sends chat request with correct headers', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: 'hi' } }],
        usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
        model: 'gpt-4o',
      }),
    })

    const p = new OpenAIProvider({
      name: 'hbscloud', type: 'openai',
      endpoint: 'https://model.hbscloud.com.cn/v1', key: 'sk-test',
    })
    const r = await p.chat([{ role: 'user', content: 'hello' }], { model: 'gpt-4o', max_tokens: 100 })

    expect(r.text).toBe('hi')
    expect(r.usage.total_tokens).toBe(15)
    expect(mockFetch).toHaveBeenCalledOnce()

    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toContain('/chat/completions')
    expect(init.method).toBe('POST')
    expect(init.headers['Authorization']).toBe('Bearer sk-test')
  })

  it('throws on non-2xx response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => 'invalid api key',
    })

    const p = new OpenAIProvider({
      name: 'openai', type: 'openai',
      endpoint: 'https://api.openai.com/v1', key: 'sk-bad',
    })
    await expect(p.chat([{ role: 'user', content: 'x' }], { model: 'gpt-4o' }))
      .rejects.toThrow(/401/)
  })

  it('listModels parses model list', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data: [{ id: 'gpt-4o' }, { id: 'gpt-3.5-turbo' }] }),
    })
    const p = new OpenAIProvider({
      name: 'openai', type: 'openai',
      endpoint: 'https://api.openai.com/v1', key: 'sk-test',
    })
    const models = await p.listModels()
    expect(models).toEqual(['gpt-4o', 'gpt-3.5-turbo'])
  })
})
