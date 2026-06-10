"""终端输出：单条 / 流式 / 进度条 / 汇总。

不依赖 rich（用 ANSI 转义）。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any, Dict, Optional

try:
    from .tracker import TokenTracker
except ImportError:  # pragma: no cover
    TokenTracker = None  # type: ignore


# ---------- 颜色 ----------

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def _tty() -> bool:
    return sys.stdout.isatty()


def colorize(s: str, color: str, *, bold: bool = False) -> str:
    if not _tty():
        return s
    return (C.BOLD if bold else "") + color + s + C.RESET


# ---------- 单条回复 ----------

def print_response(model: str, text: str, usage: Dict[str, int], latency_ms: int):
    print()
    print(colorize(f"┌─ {model}", C.CYAN, bold=True))
    for line in text.splitlines() or [""]:
        print(f"│ {line}")
    print(colorize(
        f"└─ prompt={usage.get('prompt_tokens',0)} "
        f"completion={usage.get('completion_tokens',0)} "
        f"total={usage.get('total_tokens',0)} "
        f"latency={latency_ms}ms",
        C.DIM,
    ))
    print()


def print_stream_start(model: str, max_tokens: Optional[int]):
    print(colorize(f"● {model}", C.CYAN, bold=True), end=" ", flush=True)
    if max_tokens:
        print(colorize(f"(max_tokens={max_tokens})", C.DIM), end=" ", flush=True)
    print()


def print_stream_chunk(delta: str):
    sys.stdout.write(delta)
    sys.stdout.flush()


def print_stream_end(usage: Optional[Dict[str, int]], latency_ms: int):
    print()
    if usage:
        print(colorize(
            f"  ↳ prompt={usage['prompt_tokens']} "
            f"completion={usage['completion_tokens']} "
            f"total={usage['total_tokens']} "
            f"latency={latency_ms}ms",
            C.DIM,
        ))
    else:
        print(colorize(f"  ↳ latency={latency_ms}ms (无 usage 回传)", C.DIM))
    print()


# ---------- 进度条 ----------

class ProgressBar:
    """轻量进度条（无第三方依赖）。"""
    def __init__(self, total: int, *, width: int = 30, prefix: str = "burning"):
        self.total = total
        self.width = width
        self.prefix = prefix
        self.done = 0
        self._lock = threading.Lock()
        self._t0 = time.time()

    def update(self, n: int = 1):
        with self._lock:
            self.done += n
            done, total = self.done, self.total
        pct = done / total if total else 0
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        elapsed = time.time() - self._t0
        eta = (elapsed / done) * (total - done) if done else 0
        msg = (f"\r{self.prefix} |{bar}| {done}/{total} "
               f"{pct*100:5.1f}% elapsed={elapsed:5.1f}s eta={eta:5.1f}s")
        sys.stdout.write(msg)
        sys.stdout.flush()

    def finish(self):
        sys.stdout.write("\n")
        sys.stdout.flush()


# ---------- 汇总报告 ----------

def print_summary(tracker: "TokenTracker", model: str):
    s = tracker.summary()
    print()
    print(colorize("═" * 60, C.CYAN))
    print(colorize(f"  burntoken 完成 · model={model}", C.CYAN, bold=True))
    print(colorize("═" * 60, C.CYAN))
    rows = [
        ("请求",        f"{s['ok']}/{s['requests']}  (failed={s['failed']})"),
        ("prompt tok",  f"{s['prompt_tokens']:,}"),
        ("completion",  f"{s['completion_tokens']:,}"),
        ("total tok",   f"{s['total_tokens']:,}"),
        ("耗时",        f"{s['elapsed_sec']}s"),
        ("avg latency", f"{s['avg_latency_ms']} ms"),
        ("max latency", f"{s['max_latency_ms']} ms"),
        ("吞吐",        f"{s['tps']} tok/s  ·  {s['rps']} req/s"),
        ("成本",        f"{s['cost']}"),
    ]
    for k, v in rows:
        print(f"  {colorize(k.ljust(14), C.DIM)} {colorize(v, C.GREEN, bold=True)}")
    print(colorize("═" * 60, C.CYAN))
    print()


# ---------- 落盘 ----------

class JsonlWriter:
    """把每次调用的结果写进 jsonl。"""
    def __init__(self, path: str):
        import os
        os.makedirs(path.rsplit("/", 1)[0] or ".", exist_ok=True) if "/" in path else None
        self.f = open(path, "a", encoding="utf-8")

    def write(self, obj: Dict[str, Any]):
        self.f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()
