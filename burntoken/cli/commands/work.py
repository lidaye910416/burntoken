"""`burntoken work` — real-task burn (review/docs/tests/...) with budget."""
from __future__ import annotations

import asyncio
import os
import time
import traceback
from typing import List, Optional

from ...client import ChatMessage, HBSError
from .. import AsyncHBSClient  # routed through package __getattr__ → shim
from ...reporter import JsonlWriter, ProgressBar, colorize, print_summary
from ...tasks import FileSource, GitSource, GlobSource, Item, get_task, safe_filename
from ...sources import Resolved  # noqa: F401  — used by review.py via tasks
from ...tracker import TokenTracker
from ..env import attach_log, load_env_config


def _build_source(args) -> Optional[object]:
    """根据 args 构造一个 Source（实现了 __iter__ 即可）。"""
    if args.git:
        return GitSource(mode=args.git, ref=args.git_ref)
    path = args.path
    if path == "-":
        return FileSource(path="-", max_bytes=args.max_bytes)
    if any(c in path for c in "*?["):
        pattern = path
        if args.ext:
            if "**" not in pattern:
                pattern = pattern.rstrip("/") + f"/**/*.{args.ext}"
            else:
                pattern += f".{args.ext}" if not pattern.endswith(f".{args.ext}") else ""
        return GlobSource(pattern=pattern, max_bytes=args.max_bytes, recursive=args.recursive)
    if os.path.isdir(path):
        ext = args.ext or "py"
        return GlobSource(
            pattern=os.path.join(path, f"**/*.{ext}"),
            max_bytes=args.max_bytes,
            recursive=args.recursive,
        )
    if os.path.isfile(path):
        return FileSource(path=path, max_bytes=args.max_bytes)
    return GlobSource(pattern=path, max_bytes=args.max_bytes, recursive=args.recursive)


async def cmd_work(args) -> int:
    cfg = load_env_config()
    if not cfg["api_key"]:
        print(colorize("✗ HBS_API_KEY 未设置", "\033[31m"))
        return 1
    model = args.model or cfg["model"]
    if not model:
        print(colorize("✗ 未指定模型：--model 或 HBS_MODEL", "\033[31m"))
        return 1

    try:
        task = get_task(args.task)
    except KeyError as e:
        print(colorize(f"✗ {e}", "\033[31m"))
        return 1

    print(colorize(
        f"● task={task.name}  model={model}  {task.description}", "\033[36m",
    ))

    source = _build_source(args)
    items: List[Item] = list(source) if source else []
    if not items:
        print(colorize("✗ 没有可处理的文件（检查路径/--git/--ext）", "\033[31m"))
        return 1

    if args.count:
        items = items[: args.count]
    print(colorize(f"  → {len(items)} 个文件 / 任务", "\033[36m"))

    writer: Optional[JsonlWriter] = JsonlWriter(args.save) if args.save else None
    out_dir = args.out_dir
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    max_tok_override = args.max_tokens_per_file

    tracker = TokenTracker(cfg["pricing"])
    log_sink = attach_log(tracker, args, model=model)
    progress = ProgressBar(len(items), prefix=f"work/{args.task}")
    stop_flag = {"stop": False}
    sem = asyncio.Semaphore(args.parallel)

    try:
        async with AsyncHBSClient(
            api_key=cfg["api_key"], base_url=cfg["base_url"],
            concurrency=args.parallel, verify=cfg["verify"],
        ) as client:

            async def one_item(idx: int, item: Item):
                if stop_flag["stop"]:
                    return
                async with sem:
                    if stop_flag["stop"]:
                        return
                    system, user = task.render(
                        path=item.path, content=item.content, language=item.language,
                    )
                    messages = [
                        ChatMessage("system", system),
                        ChatMessage("user", user),
                    ]
                    if log_sink:
                        log_sink.set_context(model=model, prompt=item.path)
                    t0 = time.time()
                try:
                    resp = await client.chat(
                        messages, model,
                        temperature=task.temperature,
                        max_tokens=max_tok_override or task.max_tokens,
                    )
                    latency = int((time.time() - t0) * 1000)
                    tracker.record(
                        prompt=resp.usage.prompt_tokens,
                        completion=resp.usage.completion_tokens,
                        latency_ms=latency, ok=True,
                    )
                    if out_dir:
                        fname = safe_filename(item.path, idx, task.name)
                        out_path = os.path.join(out_dir, fname)
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(f"# {task.name} · {item.path}\n\n")
                            f.write(f"> model={model}  ")
                            f.write(f"prompt={resp.usage.prompt_tokens}  ")
                            f.write(f"completion={resp.usage.completion_tokens}  ")
                            f.write(f"latency={latency}ms\n\n")
                            f.write("---\n\n")
                            f.write(resp.text)
                    if args.show:
                        print()
                        print(colorize(f"┌─ {item.path}", "\033[36m", bold=True))
                        snippet = resp.text[: args.show_chars]
                        if len(resp.text) > args.show_chars:
                            snippet += f"\n... ({len(resp.text) - args.show_chars} chars more)"
                        for line in snippet.splitlines():
                            print(f"│ {line}")
                        print()
                    if writer:
                        writer.write({
                            "type": "work",
                            "task": task.name,
                            "path": item.path,
                            "model": model,
                            "text": resp.text,
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
                        writer.write({"type": "error", "task": task.name,
                                      "path": item.path, "error": str(e)})
                    print(colorize(f"  ✗ {item.path}: {e}", "\033[31m"))
                except Exception as e:
                    tracker.record(0, 0, 0, ok=False, error=f"{type(e).__name__}: {e}")
                    if writer:
                        writer.write({"type": "error", "task": task.name,
                                      "path": item.path, "error": str(e)})
                    print(colorize(f"  ✗ {item.path}: {type(e).__name__}: {e}", "\033[31m"))
                    traceback.print_exc()
                finally:
                    progress.update(1)
                    reason = tracker.over_budget(args.max_tokens, args.max_cost)
                    if reason:
                        stop_flag["stop"] = True
                        print(colorize(f"\n⚠ 熔断：{reason}", "\033[33m"))

        tasks_list = [asyncio.create_task(one_item(i, item))
                      for i, item in enumerate(items)]

        async def watchdog():
            while True:
                await asyncio.sleep(0.2)
                if all(t.done() for t in tasks_list):
                    return
                if stop_flag["stop"]:
                    for t in tasks_list:
                        if not t.done():
                            t.cancel()
                    return
                reason = tracker.over_budget(args.max_tokens, args.max_cost)
                if reason:
                    stop_flag["stop"] = True
                    print(colorize(f"\n⚠ 熔断：{reason}", "\033[33m"))
                    for t in tasks_list:
                        if not t.done():
                            t.cancel()
                    return
        await asyncio.gather(*tasks_list, watchdog(), return_exceptions=True)
    finally:
        progress.finish()
        print_summary(tracker, model)
        if out_dir:
            print(colorize(f"✓ {len(items)} 份输出已写到：{out_dir}/", "\033[36m"))
        if writer:
            writer.close()
        if log_sink:
            log_sink.close()
    return 0
