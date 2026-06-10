"""Strategist agent：决定下一次"烧什么"。

输入：mode (meaningful|pointless|mixed) + context
输出：TaskSpec {kind, payload, model, system, max_tokens, ...}

支持两种驱动方式：
  1. preset 模式（默认）：从内置池子里抽
  2. recursive 模式：用 LLM 自身来生成 prompt（meta！）
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..tasks import TASKS, list_tasks, get_task


@dataclass
class TaskSpec:
    """一次调用的完整描述。"""
    kind: str                            # "meaningful" | "pointless"
    preset: Optional[str] = None         # code / chat / math / ...
    task: Optional[str] = None           # review / docs / tests / ...
    system: str = ""
    user: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    model: Optional[str] = None
    temperature: float = 1.0
    max_tokens: int = 512
    meta: Dict[str, Any] = field(default_factory=dict)


# --- 简单 prompt 池（pointless 用） ---
_POINTLESS_PROMPTS = [
    "用 200 字介绍一种你发明的颜色",
    "写一个关于时间旅行的悖论",
    "把 1 加到 100 等于多少？请给详细步骤",
    "描述一个不存在的城市",
    "用七言绝句写一首关于加班的诗",
    "解释为什么天空是蓝色的（编一个理由）",
    "用 Python 写一个函数把数字转成中文大写",
    "列出 7 种你从未尝试过的食物",
    "写一段广告词推销一双永远不会脏的鞋",
    "讲一个 50 字的科幻短篇",
    "用 markdown 表格对比 5 种编程语言的 hello world",
    "写一个 100 行的故事，主角是 AI 助手",
    "解释什么是 RESTful，用外卖 API 举例",
    "翻译 '好事多磨' 成英文并解释文化背景",
    "用 GoF 设计模式给一个点咖啡的场景建模",
    "为'程序员鼓励师'写一个招聘 JD",
    "从 1 到 100 找出所有的素数",
    "写一个 SQL 把每篇文章的阅读量排第 N 高的查询出来",
    "用 TypeScript 写一个 Promise.all 的 polyfill",
    "分析下 git rebase 和 merge 的区别，给出推荐",
]


class Strategist:
    """决定下一次烧什么。"""

    def __init__(self, mode: str = "meaningful", seed: Optional[int] = None,
                 custom_prompts: Optional[List[str]] = None):
        self.mode = mode
        self.rng = random.Random(seed)
        if custom_prompts:
            _POINTLESS_PROMPTS.extend(custom_prompts)

    # ---- meaningful ----

    def next_meaningful(self) -> TaskSpec:
        """从 8 个真实任务里挑一个，构造 prompt。"""
        name = self.rng.choice(list_tasks())
        task = get_task(name)
        prompts = {
            "review": [
                f"review 一下这段代码的安全问题：\n{self._fake_code()}",
                f"review 一下这段 Python 代码的 bug 风险：\n{self._fake_code()}",
            ],
            "docs": [
                f"为下面这个函数补 docstring：\n{self._fake_code()}",
            ],
            "tests": [
                f"为下面这个函数写 pytest 单元测试：\n{self._fake_code()}",
            ],
            "refactor": [
                f"重构下面这段代码，给出 BEFORE/AFTER：\n{self._fake_code()}",
            ],
            "explain": [
                f"逐行解释下面这段代码：\n{self._fake_code()}",
            ],
            "summarize": [
                "总结 Git rebase 和 merge 的区别，200 字内",
                "总结 HTTP/2 的核心改进，150 字内",
                "总结 JWT 的安全最佳实践",
            ],
            "commit": [
                f"根据以下 diff 写 commit message：\n{self._fake_diff()}",
            ],
            "translate": [
                f"把以下注释翻译成英文：\n# 加载用户配置\n# 检查权限\n# 记录操作日志",
            ],
        }
        user = self.rng.choice(prompts.get(name, ["随便聊聊"]))
        return TaskSpec(
            kind="meaningful",
            preset=None,
            task=name,
            system=task.system,
            user=user,
            temperature=task.temperature,
            max_tokens=task.max_tokens,
            meta={"source": "strategist", "real_task": name},
        )

    # ---- pointless ----

    def next_pointless(self) -> TaskSpec:
        """从 prompt 池抽一条，无意义/合成。"""
        user = self.rng.choice(_POINTLESS_PROMPTS)
        # 偶尔给点长 prompt 烧更多
        if self.rng.random() < 0.2:
            user += "\n\n请详细展开，不少于 500 字。"
        return TaskSpec(
            kind="pointless",
            preset="chat",
            task=None,
            system="你是一个助手。",
            user=user,
            temperature=1.0,
            max_tokens=self.rng.choice([128, 256, 512, 1024]),
            meta={"source": "strategist", "purpose": "burn"},
        )

    # ---- main entry ----

    def next(self) -> TaskSpec:
        if self.mode == "meaningful":
            return self.next_meaningful()
        if self.mode == "pointless":
            return self.next_pointless()
        if self.mode == "mixed":
            if self.rng.random() < 0.5:
                return self.next_meaningful()
            return self.next_pointless()
        raise ValueError(f"未知 mode: {self.mode!r}")

    # ---- 工具 ----

    def _fake_code(self) -> str:
        """生成假代码块当 review 对象。"""
        samples = [
            '''def add(a, b):
    return a + b

def divide(a, b):
    return a / b

class User:
    def __init__(self, name, age):
        self.name = name
        self.age = age
    def greet(self):
        return f"Hi {self.name}"
''',
            '''import sqlite3

def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cur.fetchone()
''',
            '''async def fetch_all(urls):
    results = []
    for url in urls:
        r = await client.get(url)
        results.append(r.json())
    return results

def process(data):
    for d in data:
        if d["score"] > 0.5:
            d["label"] = "good"
    return data
''',
        ]
        return self.rng.choice(samples)

    def _fake_diff(self) -> str:
        return '''diff --git a/main.py b/main.py
@@ -1,5 +1,7 @@
 def hello():
-    print("hello")
+    name = input("name: ")
+    print(f"hello {name}")
'''
