"""Anthropic Messages API 协议。

POST https://api.anthropic.com/v1/messages
Headers:
  x-api-key: <key>
  anthropic-version: 2023-06-01
Body:
  {"model": "...", "messages": [{"role":"user","content":"..."}],
   "max_tokens": 1024, "system": "..." (optional), "stream": false}
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

import httpx

from ..client import ChatMessage, ChatResponse, ChatChoice, CompletionUsage, StreamDelta
from .base import Provider, ProviderError


class AnthropicProvider(Provider):
    name = "anthropic"
    DEFAULT_VERSION = "2023-06-01"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com",
                 timeout: float = 180.0, max_retries: int = 3, retry_backoff: float = 1.5,
                 version: str = DEFAULT_VERSION, verify: bool = True):
        if not api_key:
            raise ValueError("api_key 不能为空")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.version = version
        self.verify = verify
        self._client = httpx.Client(
            timeout=timeout,
            verify=verify,
            headers={
                "x-api-key": api_key,
                "anthropic-version": version,
                "content-type": "application/json",
                "User-Agent": "burntoken/0.1",
            },
        )
        self._async_client: Optional[httpx.AsyncClient] = None

    async def aclose(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def _async(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.verify,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.version,
                    "content-type": "application/json",
                    "User-Agent": "burntoken/0.1",
                },
            )
        return self._async_client

    # ---- public ----

    def list_models(self) -> List[Dict[str, Any]]:
        # Anthropic 没有 list models 接口；返回硬编码列表
        return [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku"},
            {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus"},
            {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
            {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4"},
        ]

    def chat(self, messages, model, *, temperature=1.0, max_tokens=1024,
             top_p=1.0, stop=None, system=None, extra=None) -> ChatResponse:
        payload = self._build(messages, model, temperature=temperature, max_tokens=max_tokens,
                              top_p=top_p, stop=stop, system=system, stream=False, extra=extra)
        data, latency = self._post(payload)
        return self._parse(data, model, latency)

    def stream_chat(self, messages, model, **kwargs) -> Iterator[StreamDelta]:
        payload = self._build(messages, model, stream=True, **kwargs)
        url = f"{self.base_url}/v1/messages"
        with self._client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise ProviderError(resp.status_code, body)
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].lstrip()
                if not chunk:
                    continue
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield self._parse_stream(obj)

    async def achat(self, messages, model, **kwargs) -> ChatResponse:
        payload = self._build(messages, model, stream=False, **kwargs)
        data, latency = await self._apost(payload)
        return self._parse(data, model, latency)

    async def astream_chat(self, messages, model, **kwargs) -> AsyncIterator[StreamDelta]:
        payload = self._build(messages, model, stream=True, **kwargs)
        url = f"{self.base_url}/v1/messages"
        client = self._async()
        async with client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise ProviderError(resp.status_code, body)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].lstrip()
                if not chunk:
                    continue
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield self._parse_stream(obj)

    # ---- internals ----

    def _build(self, messages, model, *, temperature=1.0, max_tokens=1024,
               top_p=1.0, stop=None, system=None, stream=False, extra=None):
        # Anthropic 要求 max_tokens
        if max_tokens is None:
            max_tokens = 4096
        msgs: List[Dict[str, Any]] = []
        for m in messages:
            role = m["role"] if isinstance(m, dict) else m.role
            content = m["content"] if isinstance(m, dict) else m.content
            # Anthropic 不允许 system 在 messages 数组里；外置
            if role == "system":
                system = (system + "\n\n" + content) if system else content
                continue
            # assistant 消息：Anthropic 必须是单轮
            if role == "assistant":
                msgs.append({"role": "assistant", "content": content})
            else:
                msgs.append({"role": role, "content": content})
        payload: Dict[str, Any] = {
            "model": model, "messages": msgs, "max_tokens": max_tokens,
            "temperature": temperature, "top_p": top_p, "stream": stream,
        }
        if system:
            payload["system"] = system
        if stop is not None:
            # Anthropic 叫 stop_sequences
            payload["stop_sequences"] = stop if isinstance(stop, list) else [stop]
        if extra:
            payload.update(extra)
        return payload

    def _post(self, payload):
        return self._post_with_retry(self._client, payload)

    async def _apost(self, payload):
        return await self._apost_with_retry(self._async(), payload)

    def _post_with_retry(self, client, payload):
        url = f"{self.base_url}/v1/messages"
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                r = client.post(url, json=payload)
                latency = int((time.time() - t0) * 1000)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise ProviderError(r.status_code, r.text, f"retryable: {r.status_code}")
                if r.status_code >= 400:
                    raise ProviderError(r.status_code, r.text)
                return r.json(), latency
            except (httpx.TimeoutException, httpx.NetworkError, ProviderError) as e:
                last_err = e
                if attempt == self.max_retries:
                    raise
                time.sleep(self.retry_backoff ** attempt)
        raise last_err or ProviderError(0, "unknown")

    async def _apost_with_retry(self, client, payload):
        url = f"{self.base_url}/v1/messages"
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                r = await client.post(url, json=payload)
                latency = int((time.time() - t0) * 1000)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise ProviderError(r.status_code, r.text, f"retryable: {r.status_code}")
                if r.status_code >= 400:
                    raise ProviderError(r.status_code, r.text)
                return r.json(), latency
            except (httpx.TimeoutException, httpx.NetworkError, ProviderError) as e:
                last_err = e
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff ** attempt)
        raise last_err or ProviderError(0, "unknown")

    def _parse(self, data, requested_model, latency) -> ChatResponse:
        usage = data.get("usage") or {}
        # Anthropic: input_tokens / output_tokens
        return ChatResponse(
            id=data.get("id", f"msg_{int(time.time()*1000)}"),
            model=data.get("model", requested_model),
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=self._content_to_text(data.get("content", [])),
                    ),
                    finish_reason=self._map_stop_reason(data.get("stop_reason")),
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            ),
            created=0,
            latency_ms=latency,
        )

    def _parse_stream(self, obj) -> StreamDelta:
        delta = StreamDelta()
        ev_type = obj.get("type")
        if ev_type == "content_block_delta":
            d = obj.get("delta", {})
            if d.get("type") == "text_delta":
                delta.content = d.get("text", "")
        elif ev_type == "message_delta":
            delta.finish_reason = self._map_stop_reason(obj.get("delta", {}).get("stop_reason"))
            usage = obj.get("usage")
            if usage:
                delta.usage = CompletionUsage(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                )
        elif ev_type == "message_stop":
            delta.finish_reason = delta.finish_reason or "end_turn"
        return delta

    def _content_to_text(self, content_blocks) -> str:
        """把 Anthropic content[] 拼成纯文本。"""
        if isinstance(content_blocks, str):
            return content_blocks
        parts = []
        for blk in content_blocks or []:
            if isinstance(blk, dict) and blk.get("type") == "text":
                parts.append(blk.get("text", ""))
            elif isinstance(blk, dict) and blk.get("type") == "thinking":
                # 思考过程也带上，OpenAI 兼容性
                parts.append(f"[thinking] {blk.get('thinking','')}")
        return "".join(parts)

    def _map_stop_reason(self, reason: Optional[str]) -> str:
        return {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }.get(reason or "", "stop")
