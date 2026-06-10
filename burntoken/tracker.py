"""线程安全的 token / 成本 / 性能计数器。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TokenPricing:
    """每 1k token 的价格（CNY 或 USD 都行，调用方决定单位）。"""
    prompt_per_1k: float = 0.0
    completion_per_1k: float = 0.0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens / 1000.0) * self.prompt_per_1k \
             + (completion_tokens / 1000.0) * self.completion_per_1k


class LogEventSink:
    """把每次 tracker.record() 的事件以 JSONL 形式追加到磁盘。

    一行一个 JSON object，字段：
      timestamp, level, event, run_id, prompt, model,
      tokens (prompt/completion/total), latency_ms, cost_usd, error
    """

    def __init__(self, path: str, run_id: Optional[str] = None):
        import os
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.path = path
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._lock = threading.Lock()
        self._f = open(path, "a", encoding="utf-8")
        # 上一次 emit 时的累计 token 数，用来算单次 cost
        self._last_prompt = 0
        self._last_completion = 0
        # 上下文（每次请求前由调用方更新）
        self.model: str = ""
        self.prompt: str = ""

    def set_context(self, model: str = "", prompt: str = ""):
        """设置当前事件的上下文（model / 用户 prompt 摘要）。"""
        self.model = model
        self.prompt = prompt

    def emit(self, event: str, *, level: str = "info",
             prompt_tokens: int = 0, completion_tokens: int = 0,
             latency_ms: int = 0, error: str = "",
             **extra: Any) -> None:
        cost_usd = (prompt_tokens / 1000.0) * 0.0  # 占位；CLI 会注入实际价格
        obj: Dict[str, Any] = {
            "timestamp": time.time(),
            "level": level,
            "event": event,
            "run_id": self.run_id,
            "prompt": self.prompt,
            "model": self.model,
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            "latency_ms": latency_ms,
            "cost_usd": round(cost_usd, 6),
            "error": error,
        }
        obj.update(extra)
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.close()


@dataclass
class RunStats:
    """单次请求的统计快照。"""
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    ok: bool
    error: str = ""
    timestamp: float = field(default_factory=time.time)


class TokenTracker:
    """聚合多次调用的累计指标。

    线程安全：可用于并发 worker 模式。
    """

    def __init__(self, pricing: Optional[TokenPricing] = None):
        self._lock = threading.Lock()
        self._pricing = pricing or TokenPricing()
        self.requests_total = 0
        self.requests_ok = 0
        self.requests_failed = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.latency_sum_ms = 0
        self.latency_max_ms = 0
        self._t_start = time.time()
        self._history: list[RunStats] = []
        self._sink: Optional[LogEventSink] = None

    def attach_log(self, sink: "LogEventSink") -> None:
        """挂一个事件 sink：之后每次 record() 会同时往 sink 写一行 JSON。"""
        self._sink = sink

    def close_log(self) -> None:
        if self._sink is not None:
            self._sink.close()
            self._sink = None

    # ---- 写入 ----

    def record(self, prompt: int, completion: int, latency_ms: int, ok: bool, error: str = ""):
        s = RunStats(prompt, completion, latency_ms, ok, error)
        with self._lock:
            self.requests_total += 1
            if ok:
                self.requests_ok += 1
            else:
                self.requests_failed += 1
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.total_tokens += prompt + completion
            self.latency_sum_ms += latency_ms
            if latency_ms > self.latency_max_ms:
                self.latency_max_ms = latency_ms
            self._history.append(s)
        # sink 在锁外 emit，避免长 IO 阻塞 record() 的并发调用者
        if self._sink is not None:
            cost_usd = self._pricing.cost(prompt, completion)
            self._sink.emit(
                event="run",
                level="info" if ok else "error",
                prompt_tokens=prompt,
                completion_tokens=completion,
                latency_ms=latency_ms,
                error=error,
                cost_usd=round(cost_usd, 6),
            )

    # ---- 查询 ----

    @property
    def cost(self) -> float:
        return self._pricing.cost(self.prompt_tokens, self.completion_tokens)

    @property
    def elapsed_sec(self) -> float:
        return time.time() - self._t_start

    @property
    def avg_latency_ms(self) -> float:
        return (self.latency_sum_ms / self.requests_total) if self.requests_total else 0.0

    @property
    def tps(self) -> float:
        """每秒 token 数（输出）。"""
        return self.completion_tokens / self.elapsed_sec if self.elapsed_sec > 0 else 0.0

    @property
    def rps(self) -> float:
        return self.requests_ok / self.elapsed_sec if self.elapsed_sec > 0 else 0.0

    def history(self) -> list[RunStats]:
        with self._lock:
            return list(self._history)

    # ---- 预算检查 ----

    def over_budget(self, max_tokens: Optional[int], max_cost: Optional[float]) -> Optional[str]:
        """若超过任一阈值，返回原因；否则 None。"""
        if max_tokens is not None and self.total_tokens >= max_tokens:
            return f"tokens {self.total_tokens:,} ≥ {max_tokens:,}"
        if max_cost is not None and self.cost >= max_cost:
            return f"cost {self.cost:.4f} ≥ {max_cost:.4f}"
        return None

    def summary(self) -> dict:
        return {
            "requests": self.requests_total,
            "ok": self.requests_ok,
            "failed": self.requests_failed,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "max_latency_ms": self.latency_max_ms,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "tps": round(self.tps, 2),
            "rps": round(self.rps, 3),
            "cost": round(self.cost, 6),
        }
