"""`burntoken providers` — list all configured providers."""
from __future__ import annotations

from ...reporter import colorize
from ..env import resolve_app_config


def cmd_providers(args) -> int:
    cfg = resolve_app_config(args)
    if not cfg.providers:
        print(colorize(
            "✗ 没有任何 provider。运行 `burntoken init` 或 `burntoken config`",
            "\033[31m",
        ))
        return 1
    print(colorize(
        f"✓ {len(cfg.providers)} 个 provider，default = {cfg.default_provider}",
        "\033[36m", bold=True,
    ))
    for name, spec in cfg.providers.items():
        marker = "★" if name == cfg.default_provider else " "
        key_preview = (
            spec.api_key[:6] + "..." + spec.api_key[-4:]
            if len(spec.api_key) > 12
            else "(empty)"
        )
        print(
            f"  {marker} {name:<14s}  type={spec.type:<10s}  "
            f"model={spec.default_model:<28s}  key={key_preview}"
        )
    return 0
