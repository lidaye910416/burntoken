"""REPL interactive loop — the `/quit /reset /usage` command parser and
the per-turn chat round-trip. Lifted out of cmd_repl so it can be
tested and reused independently.
"""
from __future__ import annotations

import time
from typing import List

from ..client import ChatMessage, HBSError
from . import HBSClient  # routed through package __getattr__ → shim
from ..reporter import colorize, print_response, print_summary
from ..tracker import TokenTracker


def run_repl_loop(
    client: HBSClient,
    history: List[ChatMessage],
    model: str,
    temperature: float,
    max_tokens: int,
    max_history: int,
    tracker: TokenTracker,
    log_sink=None,
) -> None:
    """Drive the input/chat loop until the user quits or stdin closes.

    `history` is mutated in place (system msg + alternating user/assistant).
    `tracker` records per-turn usage. `log_sink` (optional) gets per-prompt
    context updates.
    """
    while True:
        try:
            line = input(colorize("» ", "\033[32m", bold=True))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        cmd = line.strip()
        if not cmd:
            continue
        if cmd in ("/quit", "/exit", "/q"):
            return
        if cmd == "/reset":
            history[:] = [m for m in history if m.role == "system"]
            print(colorize("(history cleared)", "\033[33m"))
            continue
        if cmd == "/usage":
            print_summary(tracker, model)
            continue
        history.append(ChatMessage("user", cmd))
        if log_sink:
            log_sink.set_context(model=model, prompt=cmd)
        t0 = time.time()
        try:
            resp = client.chat(
                history, model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = int((time.time() - t0) * 1000)
            print_response(model, resp.text, {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }, latency)
            tracker.record(
                resp.usage.prompt_tokens,
                resp.usage.completion_tokens,
                latency, ok=True,
            )
            history.append(ChatMessage("assistant", resp.text))
            # 控制 history 长度，避免无限增长烧爆 context
            if len(history) > 2 * max_history + 1:
                sys_msg = history[0] if history[0].role == "system" else None
                history[:] = ([sys_msg] if sys_msg else []) + history[-(2 * max_history):]
        except HBSError as e:
            tracker.record(0, 0, 0, ok=False, error=str(e))
            print(colorize(f"✗ {e}", "\033[31m"))
