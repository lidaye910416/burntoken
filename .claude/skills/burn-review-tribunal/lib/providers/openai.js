// .claude/skills/burn-review-tribunal/lib/providers/openai.js
import { Provider } from './base.js'

export class OpenAIProvider extends Provider {
  /**
   * @param {object} config
   * @param {string} config.endpoint - e.g. https://api.openai.com/v1
   */
  async chat(messages, options) {
    const url = `${this.endpoint.replace(/\/$/, '')}/chat/completions`
    const body = {
      model: options.model,
      messages,
      max_tokens: options.max_tokens ?? 1024,
      temperature: options.temperature ?? 0.2,
    }
    if (options.response_format) {
      body.response_format = options.response_format
    }

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.key}`,
      ...this.headers,
    }

    const start = Date.now()
    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout * 1000),
    })
    const latency_ms = Date.now() - start

    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`[${res.status}] ${text || res.statusText}`)
    }

    const data = await res.json()
    return {
      text: data.choices?.[0]?.message?.content ?? '',
      usage: {
        prompt_tokens: data.usage?.prompt_tokens ?? 0,
        completion_tokens: data.usage?.completion_tokens ?? 0,
        total_tokens: data.usage?.total_tokens ?? 0,
      },
      latency_ms,
      model: data.model ?? options.model,
    }
  }

  async listModels() {
    const url = `${this.endpoint.replace(/\/$/, '')}/models`
    const res = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${this.key}`,
        ...this.headers,
      },
      signal: AbortSignal.timeout(this.timeout * 1000),
    })
    if (!res.ok) {
      throw new Error(`[${res.status}] listModels failed`)
    }
    const data = await res.json()
    return (data.data ?? []).map(m => m.id)
  }
}
