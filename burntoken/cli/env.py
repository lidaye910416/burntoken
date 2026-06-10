"""Shared helpers used by every CLI command.

Centralized here so each `commands/<x>.py` stays small. Pulls together
.env loading, env config resolution, log-sink attachment, and the
provider/config resolution used by team/review/work.
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from ..config import (
    Config, ProviderSpec, load_config, load_env_fallback,
)
from ..tracker import LogEventSink, TokenPricing, TokenTracker


# ---- .env loading -------------------------------------------------------

def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k not in os.environ or not os.environ[k]:
                os.environ[k] = v


def find_env() -> Optional[str]:
    candidates = [
        os.path.expanduser("~/claude-code-hbscloud/.env"),
        os.path.expanduser("~/.claude-code-hbscloud/.env"),
        "/Users/jasonlee/claude-code-hbscloud/.env",
        os.path.join(os.getcwd(), ".env"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# ---- env config (HBS_* direct) ------------------------------------------

def _load_env_config() -> dict:
    env_path = find_env()
    if env_path:
        load_env_file(env_path)
    api_key = os.environ.get("HBS_API_KEY", "")
    base_url = os.environ.get("HBS_BASE_URL", "https://model.hbscloud.com.cn/v1")
    model = os.environ.get("HBS_MODEL", "")
    pricing = TokenPricing(
        prompt_per_1k=float(os.environ.get("HBS_PRICE_PROMPT", "0") or 0),
        completion_per_1k=float(os.environ.get("HBS_PRICE_COMPLETION", "0") or 0),
    )
    verify = os.environ.get("HBS_VERIFY", "false").strip().lower() not in ("0", "false", "no", "off")
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "pricing": pricing,
        "verify": verify,
        "env_path": env_path,
    }


# ---- app config (multi-provider) ----------------------------------------

def _resolve_app_config(args) -> Config:
    """Build a Config from CLI args: explicit path → file → .env fallback."""
    cfg_path = getattr(args, "config", None)
    cfg = load_config(cfg_path)
    if not cfg.providers:
        env = load_env_fallback()
        api_key = env.get("HBS_API_KEY", "") or os.environ.get("HBS_API_KEY", "")
        if api_key:
            cfg.providers["hbscloud"] = ProviderSpec(
                name="hbscloud", type="openai",
                api_key=api_key,
                base_url=env.get("HBS_BASE_URL", "https://model.hbscloud.com.cn/v1"),
                default_model=env.get("HBS_MODEL", "hbscloud-deepseek"),
            )
            cfg.default_provider = cfg.default_provider or "hbscloud"
    if not cfg.default_provider and len(cfg.providers) == 1:
        cfg.default_provider = next(iter(cfg.providers))
    if hasattr(args, "provider") and args.provider:
        cfg.default_provider = args.provider
    return cfg


# ---- log sink -----------------------------------------------------------

def _attach_log(tracker: TokenTracker, args, model: str = "", prompt: str = "") -> Optional[LogEventSink]:
    """If --log-file is set, attach a LogEventSink to the tracker."""
    path = getattr(args, "log_file", None)
    if not path:
        return None
    sink = LogEventSink(path)
    sink.set_context(model=model, prompt=prompt or "")
    tracker.attach_log(sink)
    return sink


__all__ = [
    "load_env_file",
    "find_env",
    "load_env_config",
    "resolve_app_config",
    "attach_log",
]


# Public aliases matching the original cli.py surface.
load_env_config = _load_env_config
resolve_app_config = _resolve_app_config
attach_log = _attach_log
