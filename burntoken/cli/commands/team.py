"""`burntoken team` — multi-agent (Strategist→Dispatcher→Accountant→Reviewer)."""
from __future__ import annotations

import asyncio

from ...agents import Team as AgentTeam, TeamConfig as AgentTeamConfig
from ...reporter import colorize
from ..env import resolve_app_config


async def _run_team(args) -> int:
    cfg = resolve_app_config(args)
    if not cfg.providers:
        print(colorize("✗ 没有 provider", "\033[31m"))
        return 1
    team_cfg = AgentTeamConfig(
        mode=args.mode,
        count=args.count,
        parallel=args.parallel,
        max_tokens=args.max_tokens,
        max_cost=args.max_cost,
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
        enable_reviewer=not args.no_reviewer,
        save=args.save,
        quiet=args.quiet,
        max_tokens_per_call=getattr(args, "max_tokens_per_file", None),
    )
    print(colorize(
        f"● team · mode={team_cfg.mode}  count={team_cfg.count}  "
        f"parallel={team_cfg.parallel}  provider={team_cfg.provider or cfg.default_provider}",
        "\033[36m", bold=True,
    ))
    print(colorize(
        "  agents:  Strategist → Dispatcher → Accountant → Reviewer",
        "\033[36m",
    ))

    team = AgentTeam(team_cfg, cfg)
    try:
        result = await team.run()
    finally:
        team.close()
    s = result["summary"]
    print()
    print(colorize("═" * 60, "\033[36m"))
    print(colorize("  team 完成", "\033[36m", bold=True))
    print(colorize("═" * 60, "\033[36m"))
    for k, v in s.items():
        if k == "by_agent":
            print(colorize("  by_agent:", "\033[33m"))
            for an, av in v.items():
                print(
                    f"    {an:<14s}  calls={av['calls']:<4d}  "
                    f"tokens={av['tokens']:<7d}  errors={av['errors']}"
                )
        else:
            print(f"  {k:<18s} {v}")
    print(colorize("═" * 60, "\033[36m"))
    return 0


def cmd_team(args) -> int:
    return asyncio.run(_run_team(args))
