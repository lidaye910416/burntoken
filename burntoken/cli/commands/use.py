"""`burntoken use <name>` — switch the default provider."""
from __future__ import annotations

from ...config import set_active
from ...reporter import colorize


def cmd_use(args) -> int:
    set_active(args.name)
    print(colorize(f"✓ default provider → {args.name}", "\033[32m"))
    print("  （永久保存到 ~/.config/burntoken/active）")
    return 0
