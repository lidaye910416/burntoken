"""`burntoken run` / bare `burntoken` — single chat call (optionally streamed)."""
from __future__ import annotations

import sys
import time
from typing import List, Optional

from ...client import ChatMessage, HBSError
from .. import HBSClient  # routed through package __getattr__ → shim
from ...presets import get as get_preset
from ...reporter import (
    JsonlWriter, colorize,
    print_response, print_stream_chunk, print_stream_end, print_stream_start,
)
from ...tracker import TokenTracker
from ..env import attach_log, load_env_config


def cmd_run(args) -> int:
    cfg = load_env_config()
    if not cfg["api_key"]:
        print(colorize("✗ HBS_API_KEY 未设置，请检查 .env", "\033[31m"))
        return 1

    model = args.model or cfg["model"]
    if not model:
        print(colorize("✗ 未指定模型：--model 或 HBS_MODEL", "\033[31m"))
        return 1

    messages: List[ChatMessage] = []
    if args.system:
        messages.append(ChatMessage("system", args.system))
    elif args.preset and args.preset != "chat":
        try:
            messages.append(ChatMessage("system", get_preset(args.preset).system))
        except KeyError:
            pass
    if args.prompt:
        messages.append(ChatMessage("user", args.prompt))

    if not messages:
        print(colorize("✗ 至少给一个 --prompt", "\033[31m"))
        return 1

    writer: Optional[JsonlWriter] = JsonlWriter(args.save) if args.save else None
    tracker = TokenTracker(cfg["pricing"])
    log_sink = attach_log(tracker, args, model=model, prompt=args.prompt or "")

    try:
        with HBSClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            verify=cfg["verify"],
        ) as client:
            try:
                if args.stream:
                    t0 = time.time()
                    print_stream_start(model, args.max_tokens)
                    content = ""
                    usage = None
                    for d in client.stream_chat(
                        messages, model,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                    ):
                        if d.content:
                            print_stream_chunk(d.content)
                            content += d.content
                        if d.usage:
                            usage = d.usage
                    latency = int((time.time() - t0) * 1000)
                    usage_dict = {
                        "prompt_tokens": usage.prompt_tokens if usage else 0,
                        "completion_tokens": usage.completion_tokens if usage else 0,
                        "total_tokens": usage.total_tokens if usage else 0,
                    }
                    print_stream_end(usage_dict, latency)
                    tracker.record(
                        prompt=usage_dict["prompt_tokens"],
                        completion=usage_dict["completion_tokens"],
                        latency_ms=latency, ok=True,
                    )
                    if writer:
                        writer.write({
                            "type": "stream", "model": model, "text": content,
                            "usage": usage_dict, "latency_ms": latency,
                        })
                else:
                    t0 = time.time()
                    resp = client.chat(
                        messages, model,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                    )
                    latency = int((time.time() - t0) * 1000)
                    usage_dict = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }
                    print_response(model, resp.text, usage_dict, latency)
                    tracker.record(
                        prompt=usage_dict["prompt_tokens"],
                        completion=usage_dict["completion_tokens"],
                        latency_ms=latency, ok=True,
                    )
                    if writer:
                        writer.write({
                            "type": "chat", "model": model, "text": resp.text,
                            "usage": usage_dict, "latency_ms": latency,
                            "finish_reason": resp.choices[0].finish_reason,
                        })
            except HBSError as e:
                tracker.record(0, 0, 0, ok=False, error=str(e))
                print(colorize(f"✗ 调用失败：{e}", "\033[31m"), file=sys.stderr)
                if writer:
                    writer.write({"type": "error", "error": str(e), "status": e.status})
                return 2
    finally:
        if writer:
            writer.close()
        if log_sink:
            log_sink.close()
    return 0
