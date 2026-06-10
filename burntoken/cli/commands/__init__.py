"""burntoken CLI subcommands.

Each module exports a `cmd_<name>(args) -> int` entry point. The
`__init__.py` re-exports the public dispatch table used by `main()`.
"""
from __future__ import annotations

from . import (
    burn, config, models, providers, repl, review, run, team, use, work,
)

DISPATCH = {
    "run": run.cmd_run,
    "burn": burn.cmd_burn,
    "repl": repl.cmd_repl,
    "models": models.cmd_models,
    "work": work.cmd_work,
    "review": review.cmd_review,
    "team": team.cmd_team,
    "providers": providers.cmd_providers,
    "use": use.cmd_use,
    "config": config.cmd_config,
}

__all__ = ["DISPATCH"]
