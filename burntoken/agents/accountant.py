"""Accountant agent：累计 token / 成本 / 错误。"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from ..tracker import TokenPricing, TokenTracker


@dataclass
class AgentStats:
    """按 agent 维度的统计。"""
    name: str
    calls: int = 0
    tokens: int = 0
    latency_ms: int = 0
    errors: int = 0


class Accountant:
    """每个 agent 都登记到 accountant；全局一份 TokenTracker 共享。"""

    def __init__(self, pricing: Optional[TokenPricing] = None):
        self.tracker = TokenTracker(pricing or TokenPricing())
        self._by_agent: dict[str, AgentStats] = {}
        self._lock = threading.Lock()

    def register(self, agent_name: str) -> None:
        with self._lock:
            if agent_name not in self._by_agent:
                self._by_agent[agent_name] = AgentStats(name=agent_name)

    def charge(self, agent: str, prompt: int, completion: int,
               latency_ms: int, ok: bool, error: str = "") -> None:
        """从某次调用扣账。"""
        self.tracker.record(prompt, completion, latency_ms, ok, error)
        with self._lock:
            s = self._by_agent.setdefault(agent, AgentStats(name=agent))
            s.calls += 1
            s.tokens += prompt + completion
            s.latency_ms += latency_ms
            if not ok:
                s.errors += 1

    def over_budget(self, max_tokens=None, max_cost=None) -> Optional[str]:
        return self.tracker.over_budget(max_tokens, max_cost)

    def report_by_agent(self) -> dict:
        with self._lock:
            return {name: vars(s) for name, s in self._by_agent.items()}

    def summary(self) -> dict:
        s = self.tracker.summary()
        s["by_agent"] = self.report_by_agent()
        return s
