"""burntoken CLI entry point.

The 983-line cli.py has been refactored into a per-command package:
- this ``__init__`` wires argparse → command dispatch
- ``parsers.py``  builds the argparse tree
- ``banner.py``   prints the interactive TLS banner
- ``env.py``      shared env / config / log-sink helpers
- ``commands/``   one module per subcommand (run, burn, repl, models, ...)

Public surface preserved: ``build_parser()`` and ``main()`` are importable
from ``burntoken.cli`` exactly as they were from the old monolithic cli.py.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .._version import __version__
from ..client import AsyncHBSClient, HBSClient, HBSError  # re-exported for patching
from .banner import is_batch_mode, print_startup_banner
from .commands import DISPATCH
from .env import load_env_config as _load_env_config

# When tests patch ``burntoken.cli.<name>`` (i.e. the shim) we need those
# patches to also be visible to the per-command modules. The shim and the
# package would otherwise have separate references. Use a PEP-562
# ``__getattr__`` on the package so attribute access for the legacy
# patch-targets (``_load_env_config``, ``HBSClient``, ``AsyncHBSClient``,
# ``HBSError``) always resolves to the shim's current value at call time.


def __getattr__(name: str):
    if name in {"_load_env_config", "HBSClient", "AsyncHBSClient", "HBSError"}:
        from burntoken import cli as _shim
        return getattr(_shim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
#  Public re-exports
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    from .parsers import build_parser as _bp
    return _bp()


# ---------------------------------------------------------------------------
#  main()
# ---------------------------------------------------------------------------

_DEFAULT_CMDS = {"run", "burn", "repl", "models", "work", "review", "team",
                 "providers", "use", "config", "-h", "--help", "--version"}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Legacy top-level flag aliases preserved from the old 983-line cli.py.
    # `burntoken --models` and `burntoken --repl` were the v0.1.0 form.
    argv = _rewrite_legacy_flags(argv)
    parser = build_parser()
    # Bare `burntoken` or unknown subcommand → default to `run`
    if not argv or argv[0] not in _DEFAULT_CMDS:
        argv = ["run"] + argv
    args = parser.parse_args(argv)
    cmd = args.cmd or "run"

    if not is_batch_mode(sys.argv[1:]):
        # Look up via the shim (``burntoken.cli``) so tests that patch
        # ``burntoken.cli._load_env_config`` take effect at call time.
        from burntoken import cli as _shim
        print_startup_banner(_shim._load_env_config())

    handler = DISPATCH.get(cmd)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


def _rewrite_legacy_flags(argv: List[str]) -> List[str]:
    """Translate v0.1.0-style top-level flags into subcommand invocations.

    ``burntoken --models``           → ``burntoken models``
    ``burntoken --repl``             → ``burntoken repl``
    ``burntoken --burntoken`` (etc)  → ``burntoken burn``
    """
    aliases = {
        "--models": "models",
        "--repl":   "repl",
    }
    if argv and argv[0] in aliases:
        argv = [aliases[argv[0]]] + argv[1:]
    return argv


__all__ = [
    "__version__",
    "build_parser",
    "main",
    # legacy name preserved for tests that patch `burntoken.cli._load_env_config`
    "_load_env_config",
]
