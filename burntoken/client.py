"""hbscloud API 客户端：同步 + 异步 + 流式。

只依赖 httpx。OpenAI Chat Completions 协议。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

import httpx


# ----------------------------- 数据类 -----------------------------

@dataclass
class CompletionUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatMessage:
    role: str  # system | user | assistant | tool
    content: str
    name: Optional[str] = None


@dataclass
class ChatChoice:
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


@dataclass
class ChatResponse:
    id: str
    model: str
    choices: List[ChatChoice]
    usage: CompletionUsage
    created: int
    latency_ms: int = 0

    @property
    def text(self) -> str:
        return self.choices[0].message.content if self.choices else ""


@dataclass
class StreamDelta:
    """流式响应里的单片 chunk。"""
    content: str = ""
    reasoning: str = ""
    finish_reason: Optional[str] = None
    usage: Optional[CompletionUsage] = None  # 仅最后一帧可能带


# ----------------------------- 异常 -----------------------------

class HBSError(Exception):
    """hbscloud 通用错误。"""
    def __init__(self, status: int, body: str, message: str = "", *, retryable: bool = False):
        self.status = status
        self.body = body
        self.message = message or body[:300]
        self.retryable = retryable
        super().__init__(f"[{status}] {self.message}")


# ----------------------------- 构造 payload -----------------------------

def _build_payload(
    messages: List[ChatMessage], model: str, *,
    temperature: float = 1.0, max_tokens: Optional[int] = None,
    top_p: float = 1.0, stop: Optional[Union[str, List[str]]] = None,
    stream: bool = False, extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
            for m in messages
        ],
        "temperature": temperature,
        "top_p": top_p,
        "stream": stream,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stop is not None:
        payload["stop"] = stop
    if extra:
        payload.update(extra)
    return payload


def _parse_response(data: Dict[str, Any], requested_model: str, latency: int) -> ChatResponse:
    usage_raw = data.get("usage") or {}
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
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        ),
        created=data.get("created", int(time.time())),
        latency_ms=latency,
    )


def _parse_stream_chunk(obj: Dict[str, Any]) -> StreamDelta:
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


# ----------------------------- 同步客户端 -----------------------------

class HBSClient:
    """hbscloud 同步客户端。

    用法:
        client = HBSClient(api_key="sk-...")
        resp = client.chat([ChatMessage("user", "hi")], model="gpt-4o")
        print(resp.text)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://model.hbscloud.com.cn/v1",
        timeout: float = 180.0,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
        verify: bool = True,
    ):
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
                "User-Agent": "burntoken/0.1 (+https://hbscloud)",
            },
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ---- public ----

    def list_models(self) -> List[Dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/models")
        r.raise_for_status()
        return r.json().get("data", [])

    def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        *,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[Union[str, List[str]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        payload = _build_payload(
            messages, model,
            temperature=temperature, max_tokens=max_tokens,
            top_p=top_p, stop=stop, stream=False, extra=extra,
        )
        data, latency = self._post_with_retry(payload)
        return _parse_response(data, model, latency)

    def stream_chat(
        self,
        messages: List[ChatMessage],
        model: str,
        *,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[Union[str, List[str]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Iterator[StreamDelta]:
        payload = _build_payload(
            messages, model,
            temperature=temperature, max_tokens=max_tokens,
            top_p=top_p, stop=stop, stream=True, extra=extra,
        )
        url = f"{self.base_url}/chat/completions"
        with self._client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise HBSError(resp.status_code, body)
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield _parse_stream_chunk(obj)

    def _post_with_retry(self, payload):
        url = f"{self.base_url}/chat/completions"
        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                r = self._client.post(url, json=payload)
                latency = int((time.time() - t0) * 1000)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise HBSError(
                        r.status_code, r.text,
                        f"retryable: {r.status_code}", retryable=True,
                    )
                if r.status_code >= 400:
                    raise HBSError(r.status_code, r.text)  # not retryable
                return r.json(), latency
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
                if attempt == self.max_retries:
                    raise
                wait = self.retry_backoff ** attempt
                time.sleep(wait)
            except HBSError as e:
                last_err = e
                if not e.retryable or attempt == self.max_retries:
                    raise
                wait = self.retry_backoff ** attempt
                time.sleep(wait)
        raise last_err or HBSError(0, "unknown error")


# ----------------------------- 异步客户端 -----------------------------

class AsyncHBSClient:
    """异步客户端：适合并发烧。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://model.hbscloud.com.cn/v1",
        timeout: float = 180.0,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
        concurrency: int = 10,
        verify: bool = True,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.concurrency = concurrency
        self.verify = verify
        self._limits = httpx.Limits(
            max_connections=concurrency * 2,
            max_keepalive_connections=concurrency,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout, limits=self._limits, verify=verify,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "burntoken/0.1 (+https://hbscloud)",
            },
        )

    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        await self.aclose()

    async def list_models(self) -> List[Dict[str, Any]]:
        r = await self._client.get(f"{self.base_url}/models")
        r.raise_for_status()
        return r.json().get("data", [])

    async def chat(self, messages, model, **kwargs) -> ChatResponse:
        payload = _build_payload(messages, model, stream=False, **kwargs)
        data, latency = await self._post_with_retry(payload)
        return _parse_response(data, model, latency)

    async def stream_chat(self, messages, model, **kwargs) -> AsyncIterator[StreamDelta]:
        payload = _build_payload(messages, model, stream=True, **kwargs)
        url = f"{self.base_url}/chat/completions"
        async with self._client.stream("POST", url, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise HBSError(resp.status_code, body)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                yield _parse_stream_chunk(obj)

    async def _post_with_retry(self, payload):
        url = f"{self.base_url}/chat/completions"
        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                r = await self._client.post(url, json=payload)
                latency = int((time.time() - t0) * 1000)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise HBSError(
                        r.status_code, r.text,
                        f"retryable: {r.status_code}", retryable=True,
                    )
                if r.status_code >= 400:
                    raise HBSError(r.status_code, r.text)  # not retryable
                return r.json(), latency
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
                if attempt == self.max_retries:
                    raise
                wait = self.retry_backoff ** attempt
                await asyncio.sleep(wait)
            except HBSError as e:
                last_err = e
                if not e.retryable or attempt == self.max_retries:
                    raise
                wait = self.retry_backoff ** attempt
                await asyncio.sleep(wait)
        raise last_err or HBSError(0, "unknown error")
