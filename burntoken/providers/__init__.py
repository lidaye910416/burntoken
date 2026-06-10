"""Provider 抽象：把 OpenAI / Anthropic 包装成统一接口。"""
from .base import Provider, ProviderError
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider


def build_provider(spec: dict) -> Provider:
    """根据 type 字段构造 provider。"""
    t = (spec.get("type") or "openai").lower()
    if t in ("openai", "openai_compatible", "openai-compatible"):
        return OpenAIProvider(
            api_key=spec["api_key"],
            base_url=spec.get("base_url", "https://api.openai.com/v1"),
            timeout=float(spec.get("timeout", 180)),
            verify=bool(spec.get("verify", True)),
        )
    if t in ("anthropic", "claude"):
        return AnthropicProvider(
            api_key=spec["api_key"],
            base_url=spec.get("base_url", "https://api.anthropic.com"),
            timeout=float(spec.get("timeout", 180)),
            verify=bool(spec.get("verify", True)),
        )
    raise ValueError(f"未知 provider type: {t!r}")


__all__ = [
    "Provider", "ProviderError",
    "OpenAIProvider", "AnthropicProvider",
    "build_provider",
]
