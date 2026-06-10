"""Provider 抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional


class ProviderError(Exception):
    """Provider 通用错误。"""
    def __init__(self, status: int, body: str, message: str = ""):
        self.status = status
        self.body = body
        self.message = message or body[:300]
        super().__init__(f"[{status}] {self.message}")


class Provider(ABC):
    """所有 provider 必须实现的统一接口。"""

    name: str = "unknown"

    @abstractmethod
    def list_models(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def chat(
        self, messages, model: str, *,
        temperature: float = 1.0, max_tokens: Optional[int] = None,
        top_p: float = 1.0, stop=None, system: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ChatResponse": ...

    @abstractmethod
    def stream_chat(
        self, messages, model: str, *,
        temperature: float = 1.0, max_tokens: Optional[int] = None,
        top_p: float = 1.0, stop=None, system: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ): ...

    @abstractmethod
    async def achat(
        self, messages, model: str, **kwargs
    ) -> "ChatResponse": ...

    @abstractmethod
    async def astream_chat(
        self, messages, model: str, **kwargs
    ) -> AsyncIterator["StreamDelta"]: ...

    def close(self):
        pass

    async def aclose(self):
        pass
