"""Dispatcher agent：负责发 API 调用。"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from ..client import ChatMessage
from ..config import Config
from ..providers import Provider, ProviderError, build_provider
from .strategist import TaskSpec


class Dispatcher:
    """用某个 provider 把 TaskSpec 真正发出去。"""

    def __init__(self, config: Config, provider_name: Optional[str] = None,
                 model: Optional[str] = None):
        spec = config.get_provider(provider_name)
        self.provider: Provider = build_provider({
            "type": spec.type,
            "api_key": spec.api_key,
            "base_url": spec.base_url,
            "timeout": spec.timeout,
        })
        self.provider_name = spec.name
        self.model = model or spec.default_model

    def dispatch(self, spec: TaskSpec) -> dict:
        """同步发一次调用。返回 {text, usage, latency_ms, model, provider}"""
        from ..client import ChatMessage
        messages = [ChatMessage("user", spec.user)] if spec.user else []
        if spec.messages:
            for m in spec.messages:
                if isinstance(m, dict):
                    messages.append(ChatMessage(m["role"], m["content"]))
        t0 = time.time()
        try:
            resp = self.provider.chat(
                messages, self.model,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                system=spec.system or None,
            )
        except ProviderError as e:
            return {
                "ok": False, "error": str(e), "status": e.status,
                "latency_ms": int((time.time() - t0) * 1000),
                "provider": self.provider_name, "model": self.model,
            }
        return {
            "ok": True,
            "text": resp.text,
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            },
            "latency_ms": resp.latency_ms,
            "provider": self.provider_name,
            "model": resp.model or self.model,
        }

    async def adispatch(self, spec: TaskSpec) -> dict:
        """异步发一次调用。

        用 asyncio.to_thread 把 sync urllib 调用跑在 thread pool，
        避免 httpx async 跟某些上游网关（hbscloud）的 SSL/连接池冲突。
        """
        import asyncio
        return await asyncio.to_thread(self.dispatch, spec)

    def close(self):
        self.provider.close()

    async def aclose(self):
        await self.provider.aclose()
