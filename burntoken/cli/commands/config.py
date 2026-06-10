"""`burntoken config show|init|path` — manage the YAML config."""
from __future__ import annotations

import json

from ...config import default_config_path, ensure_default_config
from ...reporter import colorize
from ..env import resolve_app_config


def cmd_config(args) -> int:
    if args.action == "path":
        p = default_config_path()
        print(str(p) if p else "(no config file found, run `burntoken init`)")
        return 0
    if args.action == "init":
        p = ensure_default_config()
        print(colorize(f"✓ 模板已写到 {p}", "\033[32m"))
        print("  请编辑后填入真实 api_key。")
        return 0
    if args.action == "show":
        cfg = resolve_app_config(args)
        out = {
            "config_path": cfg.config_path,
            "default_provider": cfg.default_provider,
            "providers": {
                n: {
                    "type": s.type,
                    "base_url": s.base_url,
                    "default_model": s.default_model,
                    "api_key": (s.api_key[:4] + "...") if s.api_key else "",
                    "pricing": {
                        "prompt_per_1k": s.pricing.prompt_per_1k,
                        "completion_per_1k": s.pricing.completion_per_1k,
                    },
                }
                for n, s in cfg.providers.items()
            },
            "team": vars(cfg.team),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    return 1
