// .claude/skills/burn-review-tribunal/lib/providers/base.js

/**
 * Abstract base for all model providers.
 * Subclasses must implement chat() and listModels().
 */
export class Provider {
  /**
   * @param {{
   *   name: string,
   *   type: string,
   *   endpoint: string,
   *   key: string,
   *   headers?: object,
   *   timeout?: number,
   *   insecure?: boolean,
   * }} config
   */
  constructor(config) {
    if (new.target === Provider) {
      throw new TypeError('Provider is abstract; instantiate a subclass')
    }
    this.name = config.name
    this.type = config.type
    this.endpoint = config.endpoint
    this.key = config.key
    this.headers = config.headers ?? {}
    this.timeout = config.timeout ?? 60
    this.insecure = config.insecure ?? false
  }

  /**
   * Send a chat completion request.
   *
   * @param {Array<{role: string, content: string}>} messages
   * @param {{
   *   model: string,
   *   max_tokens?: number,
   *   temperature?: number,
   *   response_format?: object,
   * }} options
   * @returns {Promise<{
   *   text: string,
   *   usage: {prompt_tokens: number, completion_tokens: number, total_tokens: number},
   *   latency_ms: number,
   *   model: string,
   * }>}
   */
  async chat(messages, options) {
    throw new Error('chat() must be implemented by subclass')
  }

  /**
   * List available models from this provider.
   *
   * @returns {Promise<string[]>}
   */
  async listModels() {
    throw new Error('listModels() must be implemented by subclass')
  }
}
