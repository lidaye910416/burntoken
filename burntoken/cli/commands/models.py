"""`burntoken models` — list models on the configured provider."""
from __future__ import annotations

from ...client import HBSError
from .. import HBSClient  # routed through package __getattr__ → shim
from ...reporter import colorize
from ..env import load_env_config


def cmd_models(args) -> int:
    cfg = load_env_config()
    if not cfg["api_key"]:
        print(colorize("✗ HBS_API_KEY 未设置", "\033[31m"))
        return 1
    with HBSClient(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        verify=cfg["verify"],
    ) as client:
        try:
            models = client.list_models()
        except HBSError as e:
            print(colorize(f"✗ {e}", "\033[31m"))
            return 1
    print(colorize(
        f"✓ {len(models)} 个模型 @ {cfg['base_url']}:",
        "\033[36m", bold=True,
    ))
    for m in models:
        print(f"  - {m.get('id')}  ({m.get('owned_by', '?')})")
    return 0
