"""`burntoken review` — high-level: local / github:user/repo / URL → cmd_work."""
from __future__ import annotations

import argparse
import asyncio
import os

from ...reporter import colorize
from ...sources import resolve_target
from . import work as work_cmd


def cmd_review(args) -> int:
    """Resolve the target (path / github:user/repo / URL / stdin), then
    delegate to `work review` via a constructed Namespace."""
    try:
        resolved = resolve_target(
            args.target,
            ref=args.ref,
            refresh=args.refresh,
            no_cache=args.no_cache,
            cache_dir=args.cache_dir,
            print_actions=True,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(colorize(f"✗ {e}", "\033[31m"))
        return 1

    if resolved.kind == "stdin":
        print(colorize("● review via stdin", "\033[36m"))
    else:
        print(colorize(
            f"● review · {resolved.kind} · {resolved.display_name} · {resolved.local_path}",
            "\033[36m",
        ))

    out_dir = None
    if args.out_dir:
        out_dir = os.path.join(args.out_dir, f"{resolved.kind}__{resolved.display_name}")
        print(colorize(f"  → out_dir = {out_dir}", "\033[36m"))

    work_args = argparse.Namespace(
        task="review",
        path=resolved.local_path if resolved.kind != "stdin" else "-",
        git=None,
        git_ref=args.ref,
        ext=args.ext,
        recursive=args.recursive,
        model=args.model,
        count=args.count,
        parallel=args.parallel,
        max_tokens=args.max_tokens,
        max_cost=args.max_cost,
        max_tokens_per_file=args.max_tokens_per_file,
        max_bytes=args.max_bytes,
        save=args.save,
        out_dir=out_dir,
        show=args.show,
        show_chars=args.show_chars,
        seed=args.seed,
    )
    return asyncio.run(work_cmd.cmd_work(work_args))
