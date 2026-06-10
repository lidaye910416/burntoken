"""Backwards-compatibility shim. Use `burntoken.cli` (the package) instead."""
from __future__ import annotations

from .cli import (
    AsyncHBSClient,
    HBSClient,
    HBSError,
    __version__,
    _load_env_config,
    build_parser,
    main,
)

__all__ = [
    "main",
    "build_parser",
    "__version__",
    "_load_env_config",
    "HBSClient",
    "AsyncHBSClient",
    "HBSError",
]
