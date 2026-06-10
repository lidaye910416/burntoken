"""Startup banner: prints a TLS-verify hint when run interactively."""
from __future__ import annotations

import sys

from ..reporter import colorize


def print_startup_banner(env_config: dict) -> None:
    """Print the interactive startup banner if we're attached to a TTY.

    Caller decides whether to call this at all (typically: skip when
    --batch was passed or stdin is not a TTY).
    """
    if env_config["verify"]:
        print(colorize("HBS TLS verify: on", "\033[36m"))
    else:
        print("HBS TLS verify: off (set HBS_VERIFY=true to enable)")


def is_batch_mode(argv: list[str]) -> bool:
    """Return True if we should suppress the interactive banner."""
    return "--batch" in argv or not sys.stdin.isatty()
