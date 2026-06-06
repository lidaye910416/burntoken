// .claude/skills/burn-review-tribunal/lib/providers/anthropic.js
import { Provider } from './base.js'

const ANTHROPIC_VERSION = '2023-06-01'

export class AnthropicProvider extends Provider {
  async chat(messages, options) {
    const url = `${this.endpoint.replace(/\/$/, '')}/v1/messages`

    // Anthropic API: system message is a separate field
    const systemMsg = messages.find(m => m.role === 'system')
    const userMessages = messages.filter(m => m.role !== 'system')

    const body = {
      model: options.model,
      max_tokens: options.max_tokens ?? 1024,
      temperature: options.temperature ?? 0.2,
      messages: userMessages,
    }
    if (systemMsg) {
      body.system = systemMsg.content
    }

    const headers = {
      'Content-Type': 'application/json',
      'x-api-key': this.key,
      'anthropic-version': ANTHROPIC_VERSION,
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
    const text = (data.content ?? [])
      .filter(c => c.type === 'text')
      .map(c => c.text)
      .join('')

    return {
      text,
      usage: {
        prompt_tokens: data.usage?.input_tokens ?? 0,
        completion_tokens: data.usage?.output_tokens ?? 0,
        total_tokens: (data.usage?.input_tokens ?? 0) + (data.usage?.output_tokens ?? 0),
      },
      latency_ms,
      model: data.model ?? options.model,
    }
  }

  async listModels() {
    // Anthropic doesn't have a public list endpoint; return known models
    return [
      'claude-3-5-sonnet-20241022',
      'claude-3-5-sonnet-20240620',
      'claude-3-haiku-20240307',
      'claude-3-opus-20240229',
    ]
  }
}
