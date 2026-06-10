"""Team 编排器：把 4 个 agent 串成工作流。"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional

from ..config import Config
from ..tracker import TokenPricing
from .accountant import Accountant
from .dispatcher import Dispatcher
from .reviewer import Reviewer
from .strategist import Strategist, TaskSpec


@dataclass
class TeamConfig:
    mode: str = "meaningful"             # meaningful | pointless | mixed
    count: int = 10                      # 总轮数
    parallel: int = 2                     # 并发
    max_tokens: Optional[int] = None     # 累计 token 熔断
    max_cost: Optional[float] = None     # 累计成本熔断
    provider: Optional[str] = None       # 用哪个 provider
    model: Optional[str] = None
    enable_reviewer: bool = True
    save: Optional[str] = None           # jsonl
    quiet: bool = False                  # 不打每次明细
    max_tokens_per_call: Optional[int] = None  # 单次调用的 max_tokens 覆盖


class Team:
    """4 个 agent 协同。"""

    def __init__(self, config: TeamConfig, app_config: Config):
        self.cfg = config
        self.app = app_config

        # ----- 初始化 4 个 agent -----
        spec = app_config.get_provider(config.provider)
        pricing = spec.pricing
        self.strategist = Strategist(mode=config.mode)
        self.dispatcher = Dispatcher(app_config, config.provider, config.model)
        self.accountant = Accountant(pricing)
        self.reviewer = Reviewer(enabled=config.enable_reviewer)

        for name in ("strategist", "dispatcher", "reviewer"):
            self.accountant.register(name)

    # ---- 单轮 ----

    def step(self) -> dict:
        """同步跑一整轮。返回结果字典。"""
        # Strategist
        task: TaskSpec = self.strategist.next()
        # Dispatcher
        result = self.dispatcher.dispatch(task)
        # Accountant
        if result.get("ok"):
            u = result["usage"]
            self.accountant.charge("dispatcher", u["prompt_tokens"],
                                   u["completion_tokens"],
                                   result["latency_ms"], True)
        else:
            self.accountant.charge("dispatcher", 0, 0,
                                   result.get("latency_ms", 0),
                                   False, result.get("error", ""))
        # Reviewer
        if result.get("ok"):
            passed, reason = self.reviewer.check(task, result["text"])
        else:
            passed, reason = False, "dispatch failed"
        return {
            "task_kind": task.kind,
            "task_preset": task.preset,
            "task_name": task.task,
            "user": task.user,
            "model": result.get("model", self.dispatcher.model),
            "provider": result.get("provider", self.dispatcher.provider_name),
            "ok": result.get("ok", False),
            "error": result.get("error", ""),
            "text": result.get("text", ""),
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "review_passed": passed,
            "review_reason": reason,
        }

    async def astep(self) -> dict:
        task = self.strategist.next()
        if self.cfg.max_tokens_per_call is not None:
            task.max_tokens = self.cfg.max_tokens_per_call
        result = await self.dispatcher.adispatch(task)
        if result.get("ok"):
            u = result["usage"]
            self.accountant.charge("dispatcher", u["prompt_tokens"],
                                   u["completion_tokens"],
                                   result["latency_ms"], True)
        else:
            self.accountant.charge("dispatcher", 0, 0,
                                   result.get("latency_ms", 0),
                                   False, result.get("error", ""))
        if result.get("ok"):
            passed, reason = self.reviewer.check(task, result["text"])
        else:
            passed, reason = False, "dispatch failed"
        return {
            "task_kind": task.kind,
            "task_preset": task.preset,
            "task_name": task.task,
            "user": task.user,
            "model": result.get("model", self.dispatcher.model),
            "provider": result.get("provider", self.dispatcher.provider_name),
            "ok": result.get("ok", False),
            "error": result.get("error", ""),
            "text": result.get("text", ""),
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "review_passed": passed,
            "review_reason": reason,
        }

    # ---- 主循环 ----

    async def run(self) -> dict:
        sem = asyncio.Semaphore(self.cfg.parallel)
        results: List[dict] = []
        stop = {"flag": False}

        async def one_round(idx: int):
            if stop["flag"]:
                return
            async with sem:
                if stop["flag"]:
                    return
                t0 = time.time()
                r = await self.astep()
                wall = int((time.time() - t0) * 1000)
                if not self.cfg.quiet:
                    tag = f"{r['task_kind']:<10s}  {r['task_name'] or r['task_preset'] or '-':<8s}"
                    if r["ok"]:
                        u = r["usage"]
                        status = colorize("✓", "\033[32m", bold=True)
                    else:
                        status = colorize("✗", "\033[31m", bold=True)
                    print(f"  [{idx+1:>3d}/{self.cfg.count}] {status}  "
                          f"{tag}  {r['model']:<20s}  "
                          f"in={u.get('prompt_tokens',0):>5}  "
                          f"out={u.get('completion_tokens',0):>5}  "
                          f"{r['latency_ms']:>5}ms  "
                          f"wall={wall}ms")
                results.append(r)
                # 熔断
                reason = self.accountant.over_budget(self.cfg.max_tokens, self.cfg.max_cost)
                if reason:
                    stop["flag"] = True
                    print(colorize(f"\n  ⚠ team 熔断：{reason}", "\033[33m"))

        tasks = [asyncio.create_task(one_round(i)) for i in range(self.cfg.count)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 保存
        if self.cfg.save:
            import json, os
            if "/" in self.cfg.save:
                os.makedirs(self.cfg.save.rsplit("/", 1)[0], exist_ok=True)
            with open(self.cfg.save, "a", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return {"results": results, "summary": self.accountant.summary()}

    def close(self):
        self.dispatcher.close()


def colorize(s, c, *, bold=False):
    try:
        import sys
        if not sys.stdout.isatty():
            return s
    except Exception:
        return s
    b = "\033[1m" if bold else ""
    return f"{b}{c}{s}\033[0m"
