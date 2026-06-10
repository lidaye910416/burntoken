"""`burntoken burn` — N requests, P parallel, with budget watchdog."""
from __future__ import annotations

import asyncio
import random
import time
from typing import List, Optional

from ...client import ChatMessage, HBSError
from .. import AsyncHBSClient  # routed through package __getattr__ → shim
from ...presets import get as get_preset, longctx_filler
from ...reporter import JsonlWriter, ProgressBar, colorize, print_summary
from ...tracker import TokenTracker
from ..env import attach_log, load_env_config


async def _burn_async(args) -> int:
    cfg = load_env_config()
    if not cfg["api_key"]:
        print(colorize("✗ HBS_API_KEY 未设置", "\033[31m"))
        return 1
    model = args.model or cfg["model"]
    if not model:
        print(colorize("✗ 未指定模型", "\033[31m"))
        return 1

    preset = get_preset(args.preset)
    rng = random.Random(args.seed)
    writer: Optional[JsonlWriter] = JsonlWriter(args.save) if args.save else None
    tracker = TokenTracker(cfg["pricing"])
    log_sink = attach_log(tracker, args, model=model)
    progress = ProgressBar(args.count, prefix=f"burntoken/{args.preset}")

    sem = asyncio.Semaphore(args.parallel)
    stop_flag = {"stop": False}

    try:
        async with AsyncHBSClient(
            api_key=cfg["api_key"], base_url=cfg["base_url"],
            concurrency=args.parallel, verify=cfg["verify"],
        ) as client:

            async def one_call(idx: int):
                if stop_flag["stop"]:
                    return
                async with sem:
                    if stop_flag["stop"]:
                        return
                    prompt, max_tok, temp = preset.sample(rng)
                    messages: List[ChatMessage] = []
                    if preset.system:
                        messages.append(ChatMessage("system", preset.system))
                    if args.preset == "longctx":
                        for role, content in longctx_filler(seed=idx, rounds=args.multi_turn):
                            messages.append(ChatMessage(role, content))
                    messages.append(ChatMessage("user", prompt))
                    if log_sink:
                        log_sink.set_context(model=model, prompt=prompt)
                    t0 = time.time()
                    try:
                        resp = await client.chat(
                            messages, model,
                            temperature=temp,
                            max_tokens=max_tok,
                        )
                        latency = int((time.time() - t0) * 1000)
                        tracker.record(
                            prompt=resp.usage.prompt_tokens,
                            completion=resp.usage.completion_tokens,
                            latency_ms=latency, ok=True,
                        )
                        if writer:
                            writer.write({
                                "type": "burn", "idx": idx, "model": model,
                                "preset": args.preset, "text": resp.text,
                                "usage": {
                                    "prompt_tokens": resp.usage.prompt_tokens,
                                    "completion_tokens": resp.usage.completion_tokens,
                                    "total_tokens": resp.usage.total_tokens,
                                },
                                "latency_ms": latency,
                            })
                    except HBSError as e:
                        tracker.record(0, 0, 0, ok=False, error=str(e))
                        if writer:
                            writer.write({"type": "error", "idx": idx, "error": str(e)})
                    finally:
                        progress.update(1)
                        reason = tracker.over_budget(args.max_tokens, args.max_cost)
                        if reason:
                            stop_flag["stop"] = True
                            print(colorize(f"\n⚠ 触发熔断：{reason}", "\033[33m"))

            tasks = [asyncio.create_task(one_call(i)) for i in range(args.count)]

            async def watchdog():
                while True:
                    await asyncio.sleep(0.2)
                    if all(t.done() for t in tasks):
                        return
                    if stop_flag["stop"]:
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return
                    reason = tracker.over_budget(args.max_tokens, args.max_cost)
                    if reason:
                        stop_flag["stop"] = True
                        print(colorize(f"\n⚠ 触发熔断：{reason}", "\033[33m"))
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return
            await asyncio.gather(*tasks, watchdog(), return_exceptions=True)
    finally:
        progress.finish()
        print_summary(tracker, model)
        if writer:
            writer.close()
        if log_sink:
            log_sink.close()
    return 0


def cmd_burn(args) -> int:
    return asyncio.run(_burn_async(args))
