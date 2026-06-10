"""OpenAI Chat Completions 协议（兼容 hbscloud、OpenAI 官方等）。"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
import ssl
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

import httpx

from ..client import (
    ChatMessage, ChatResponse, CompletionUsage, StreamDelta,
)
from .base import Provider, ProviderError


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 timeout: float = 180.0, max_retries: int = 3, retry_backoff: float = 1.5,
                 verify: bool = True):
        if not api_key:
            raise ValueError("api_key 不能为空")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.verify = verify
        self._client = httpx.Client(
            timeout=timeout,
            verify=verify,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "burntoken/0.1",
            },
        )
        self._async_client: Optional[httpx.AsyncClient] = None

    def close(self):
        self._client.close()
        if self._async_client:
            # sync close, async version needs aclose()
            pass

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
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "burntoken/0.1",
                },
            )
        return self._async_client

    # ---- public sync ----

    def list_models(self) -> List[Dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/models")
        r.raise_for_status()
        return r.json().get("data", [])

    def chat(self, messages, model, *, temperature=1.0, max_tokens=None,
             top_p=1.0, stop=None, system=None, extra=None) -> ChatResponse:
        payload = self._build(messages, model, temperature=temperature, max_tokens=max_tokens,
                              top_p=top_p, stop=stop, system=system, stream=False, extra=extra)
        data, latency = self._post(payload)
        return self._parse(data, model, latency)

    def stream_chat(self, messages, model, *, temperature=1.0, max_tokens=None,
                    top_p=1.0, stop=None, system=None, extra=None) -> Iterator[StreamDelta]:
        payload = self._build(messages, model, temperature=temperature, max_tokens=max_tokens,
                              top_p=top_p, stop=stop, system=system, stream=True, extra=extra)
        url = f"{self.base_url}/chat/completions"
        with self._client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise ProviderError(resp.status_code, body)
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].lstrip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield self._parse_stream(obj)

    # ---- public async ----

    async def achat(self, messages, model, **kwargs) -> ChatResponse:
        payload = self._build(messages, model, stream=False, **kwargs)
        data, latency = await self._apost(payload)
        return self._parse(data, model, latency)

    async def astream_chat(self, messages, model, **kwargs) -> AsyncIterator[StreamDelta]:
        payload = self._build(messages, model, stream=True, **kwargs)
        url = f"{self.base_url}/chat/completions"
        client = self._async()
        async with client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise ProviderError(resp.status_code, body)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].lstrip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield self._parse_stream(obj)

    # ---- internals ----

    def _build(self, messages, model, *, temperature=1.0, max_tokens=None,
               top_p=1.0, stop=None, system=None, stream=False, extra=None):
        msgs: List[Dict[str, Any]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            if isinstance(m, dict):
                msgs.append(m)
            else:
                msgs.append({"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})})
        payload: Dict[str, Any] = {
            "model": model, "messages": msgs,
            "temperature": temperature, "top_p": top_p, "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop
        if extra:
            payload.update(extra)
        return payload

    def _post(self, payload):
        return self._post_urllib(payload)

    async def _apost(self, payload):
        return await self._apost_with_retry(self._async(), payload)

    def _post_urllib(self, payload):
        """走 urllib（hbscloud 证书场景下 httpx 同步连接池有问题）。"""
        import urllib.request
        import ssl
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ctx = ssl.create_default_context()
        if not self.verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                req = urllib.request.Request(
                    url, data=body, method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "burntoken/0.1",
                    },
                )
                r = urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
                text = r.read().decode("utf-8")
                latency = int((time.time() - t0) * 1000)
                data = json.loads(text)
                # urllib 没有 status code 概念；2xx = 成功
                if "error" in data and "choices" not in data:
                    raise ProviderError(500, text)
                return data, latency
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code == 429 or 500 <= e.code < 600:
                    last_err = ProviderError(e.code, body_text, f"retryable: {e.code}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_backoff ** attempt)
                        continue
                raise ProviderError(e.code, body_text)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = ProviderError(0, str(e))
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff ** attempt)
                    continue
                raise last_err
        raise last_err or ProviderError(0, "unknown")

    async def _apost_with_retry(self, client, payload):
        url = f"{self.base_url}/chat/completions"
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
        from ..client import ChatChoice
        usage = data.get("usage") or {}
        return ChatResponse(
            id=data.get("id", f"chatcmpl-{int(time.time()*1000)}"),
            model=data.get("model", requested_model),
            choices=[
                ChatChoice(
                    index=c.get("index", i),
                    message=ChatMessage(
                        role=c.get("message", {}).get("role", "assistant"),
                        content=c.get("message", {}).get("content", "") or "",
                    ),
                    finish_reason=c.get("finish_reason", "stop"),
                )
                for i, c in enumerate(data.get("choices", []))
            ],
            usage=CompletionUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            created=data.get("created", int(time.time())),
            latency_ms=latency,
        )

    def _parse_stream(self, obj) -> StreamDelta:
        delta = StreamDelta()
        choices = obj.get("choices") or []
        if choices:
            d = choices[0].get("delta", {}) or {}
            delta.content = d.get("content", "") or ""
            delta.reasoning = d.get("reasoning_content", "") or ""
            delta.finish_reason = choices[0].get("finish_reason")
        usage = obj.get("usage")
        if usage:
            delta.usage = CompletionUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        return delta
