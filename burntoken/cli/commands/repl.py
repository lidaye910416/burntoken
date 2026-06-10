"""`burntoken repl` — interactive chat loop with /quit /reset /usage."""
from __future__ import annotations

from typing import List

from ...client import ChatMessage
from .. import HBSClient  # routed through package __getattr__ → shim
from ...reporter import colorize, print_summary
from ...tracker import TokenTracker
from ..env import attach_log, load_env_config
from ..repl_loop import run_repl_loop


def cmd_repl(args) -> int:
    cfg = load_env_config()
    if not cfg["api_key"]:
        print(colorize("✗ HBS_API_KEY 未设置", "\033[31m"))
        return 1
    model = args.model or cfg["model"]
    if not model:
        print(colorize("✗ 未指定模型", "\033[31m"))
        return 1

    print(colorize(
        f"burntoken REPL · model={model} · /quit 退出 /reset 清空 /usage 统计",
        "\033[36m", bold=True,
    ))
    history: List[ChatMessage] = []
    if args.system:
        history.append(ChatMessage("system", args.system))
    tracker = TokenTracker(cfg["pricing"])
    log_sink = attach_log(tracker, args, model=model)

    try:
        with HBSClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            verify=cfg["verify"],
        ) as client:
            run_repl_loop(
                client=client,
                history=history,
                model=model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                max_history=args.max_history,
                tracker=tracker,
                log_sink=log_sink,
            )
    finally:
        print_summary(tracker, model)
        if log_sink:
            log_sink.close()
    return 0
