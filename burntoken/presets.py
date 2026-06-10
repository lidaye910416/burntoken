"""5 种预设烧法：覆盖短答 / 长文 / 代码 / 长上下文 / 闲聊。

每个 preset 是一组 (system, user_template, params)：
- user_template 里的 {seed} 会被外部循环里的随机种子替换
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class Preset:
    name: str
    description: str
    system: str = ""
    user_templates: List[str] = field(default_factory=list)
    temperature: float = 1.0
    max_tokens: int = 512

    def sample(self, rng: random.Random) -> Tuple[str, int, float]:
        tpl = rng.choice(self.user_templates)
        seed = rng.randint(1, 10_000_000)
        return (tpl.format(seed=seed), self.max_tokens, self.temperature)


# ----------- 内置预设 -----------

_PRESETS: Dict[str, Preset] = {
    "chat": Preset(
        name="chat",
        description="闲聊型：短问短答，测基本响应延迟",
        system="你是一个友好的中文助手，回答简洁。",
        user_templates=[
            "用一句话说 hello",
            "今天上海天气怎么样？",
            "推荐一部科幻电影",
            "给我讲个笑话",
            "用中文写一句诗",
            "解释一下'内卷'是什么意思",
            "推荐一道简单的家常菜",
            "用一句话安慰一个加班的人",
        ],
        temperature=1.0, max_tokens=128,
    ),
    "math": Preset(
        name="math",
        description="数学推理：测 CoT 能力",
        system="你是一个严谨的数学家，请一步步推理。",
        user_templates=[
            "求 ∫(0,1) x^2 dx = ?",
            "一个班 50 人，及格率 84%，不及格几人？",
            "斐波那契数列第 20 项是多少？",
            "已知 a+b=10, a-b=4, 求 a*b",
            "解方程 x^2 - 5x + 6 = 0",
            "log₂(256) = ?",
            "一个圆半径 5，面积多少？（π 取 3.14）",
            "从 1 加到 100 等于多少？",
        ],
        temperature=0.3, max_tokens=512,
    ),
    "code": Preset(
        name="code",
        description="代码生成：测 tool-less 代码能力",
        system="你是一个 Python 专家。",
        user_templates=[
            "写一个 Python 函数判断回文串",
            "用 Python 实现二分查找",
            "写一段代码读取 JSON 文件并打印每条记录",
            "Python 中 GIL 是什么？一句话回答",
            "写一个 async 函数并发抓取 3 个 URL",
            "用 Python 计算 1!+2!+...+10!",
            "写一个装饰器统计函数耗时",
            "解释 list 和 tuple 的区别，3 行内",
        ],
        temperature=0.4, max_tokens=768,
    ),
    "essay": Preset(
        name="essay",
        description="长文输出：测 max_tokens 边界和长输出成本",
        system="你是一个中文作家，文笔流畅。",
        user_templates=[
            "以'城市的雨夜'为题写 300 字散文",
            "写一段关于 AI 与教育的 200 字评论",
            "用 400 字介绍量子计算的基本原理",
            "写一首 7 言 4 句的现代诗，主题：种子(seed={seed})",
            "用 250 字描述一道经典川菜的做法",
            "为一款国产开源 IDE 写一段 200 字产品介绍",
        ],
        temperature=0.9, max_tokens=2048,
    ),
    "longctx": Preset(
        name="longctx",
        description="长上下文：往 messages 里灌 N 段对话，测大输入成本",
        system="你是一个细心的阅读理解助手。",
        user_templates=[
            # 由 longctx_run 模式动态填充
            "请总结以上所有对话的核心观点，用 3 句话。",
        ],
        temperature=0.5, max_tokens=512,
    ),
}


def get(name: str) -> Preset:
    if name not in _PRESETS:
        raise KeyError(f"未知预设：{name}，可选：{list(_PRESETS)}")
    return _PRESETS[name]


def list_names() -> List[str]:
    return list(_PRESETS.keys())


def longctx_filler(seed: int, rounds: int = 10) -> List[Tuple[str, str]]:
    """生成 N 轮 user/assistant 假对话（只取 user 当历史）。"""
    rng = random.Random(seed)
    topics = ["咖啡", "健身", "摄影", "旅行", "编程", "美食", "宠物", "音乐", "电影", "读书"]
    out: List[Tuple[str, str]] = []
    for i in range(rounds):
        t = topics[(seed + i) % len(topics)]
        out.append(("user", f"第 {i+1} 轮：你对 '{t}' 有什么看法？"))
        out.append(("assistant", f"关于 {t}，我觉得…（第 {i+1} 轮回复）"))
    return out


# ----------- 烧法编排 -----------

@dataclass
class BurnPlan:
    """一次 burntoken 的总计划。"""
    preset: Preset
    n_requests: int
    parallel: int
    multi_turn: int = 1  # longctx 模式用：往历史里塞 N 轮


def make_plan(preset_name: str, count: int, parallel: int, multi_turn: int = 1) -> BurnPlan:
    return BurnPlan(
        preset=get(preset_name),
        n_requests=count,
        parallel=parallel,
        multi_turn=multi_turn,
    )
