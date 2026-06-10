"""真实任务定义 + 输入源。

让 burntoken 不再是空 prompt 烧模板，而是真的让模型干活：
- review / docs / tests / refactor / explain / summarize / commit / translate
- 输入：单文件 / glob / git diff / stdin
"""
from __future__ import annotations

import glob as _glob
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple


# ============================================================================
#  RealTask
# ============================================================================

@dataclass
class RealTask:
    """一次"真任务"的完整定义。"""
    name: str
    description: str
    system: str                          # system prompt
    user_template: str                   # user prompt 模板，用 {path} {content} {language} 占位
    temperature: float = 0.4
    max_tokens: int = 2048

    def render(self, *, path: str, content: str, language: str = "") -> Tuple[str, str]:
        """把模板填成 (system, user) 两段。"""
        # 用 str.replace 而不是 str.format，避开代码里大量 { } 干扰
        user = (self.user_template
                .replace("{path}", path)
                .replace("{content}", content)
                .replace("{language}", language))
        return self.system, user


# ---------------- 8 个内置任务 ----------------

TASKS: Dict[str, RealTask] = {}

TASKS["review"] = RealTask(
    name="review",
    description="代码 review：列出 bug / 安全 / 性能 / 风格问题 + 改进建议",
    system=(
        "你是一位严谨的高级工程师，正在 review 同事的代码。"
        "请给出具体、可执行、有理有据的反馈。"
        "中文输出，必要时附最小代码示例。"
    ),
    user_template=(
        "请对以下文件做代码 review：\n"
        "- 路径：`{path}`\n"
        "- 语言：{language}\n\n"
        "按以下结构输出（必须覆盖每一节，**没有就写'无'**）：\n\n"
        "## 1. 🐞 Bug 风险\n"
        "## 2. 🔒 安全问题\n"
        "## 3. ⚡ 性能\n"
        "## 4. 📖 可读性 / 风格\n"
        "## 5. 🧪 可测试性\n"
        "## 6. ✅ 必须改（高优先级）\n"
        "## 7. 💡 建议改（中低优先级）\n"
        "## 8. ✨ 亮点（值得保留的设计）\n\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.3, max_tokens=4096,
)

TASKS["docs"] = RealTask(
    name="docs",
    description="为 public 函数/类生成 docstring（Google 风格），保持代码结构",
    system="你是一个文档专家。生成清晰、完整、含 example 的 docstring。",
    user_template=(
        "为以下文件的 **所有 public 函数/类/方法** 生成/改进 docstring。\n"
        "文件：`{path}`\n\n"
        "要求：\n"
        "- 使用 Google 风格 docstring\n"
        "- 包含 Args / Returns / Raises（适用时）\n"
        "- 至少一个 Example\n"
        "- **保持原有代码结构**，不要修改逻辑\n"
        "- 输出**完整的修改后文件**，不要省略\n\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.2, max_tokens=4096,
)

TASKS["tests"] = RealTask(
    name="tests",
    description="为文件中的 public 函数/类生成 pytest 单元测试",
    system="你是一个测试工程师，专精 pytest。生成的测试要可独立运行。",
    user_template=(
        "为以下文件生成完整单元测试。\n"
        "文件：`{path}`\n\n"
        "要求：\n"
        "- 覆盖正常路径 / 边界条件 / 异常\n"
        "- 使用 pytest（不要 unittest）\n"
        "- 必要时使用 unittest.mock\n"
        "- 输出**完整可运行**的测试文件，import 都齐全\n"
        "- 文件名建议：`test_{path_basename}`\n\n"
        "源代码：\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.3, max_tokens=4096,
)

TASKS["refactor"] = RealTask(
    name="refactor",
    description="提出具体重构建议，给 BEFORE/AFTER 对比",
    system=(
        "你是 15 年经验的架构师，专精重构。"
        "所有建议必须保留外部行为不变（refactor，不是 rewrite）。"
    ),
    user_template=(
        "对以下文件提出具体重构建议。\n"
        "文件：`{path}`\n\n"
        "输出格式：\n"
        "### 重构 N：<一句话标题>\n"
        "**原因**：...\n"
        "**BEFORE**：\n```\n...\n```\n"
        "**AFTER**：\n```\n...\n```\n"
        "**收益**：...\n\n"
        "源代码：\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.4, max_tokens=4096,
)

TASKS["explain"] = RealTask(
    name="explain",
    description="逐段解释代码，markdown 格式，可教学用",
    system="你是一个耐心的老师，给初学者讲代码。",
    user_template=(
        "请逐段解释以下文件。\n"
        "文件：`{path}`\n\n"
        "要求：\n"
        "- 标注每个函数/类的用途\n"
        "- 解释关键设计决策\n"
        "- 控制流用文字图示或表格\n"
        "- 公共 API 单独列一节\n\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.4, max_tokens=4096,
)

TASKS["summarize"] = RealTask(
    name="summarize",
    description="200 字内总结文件核心功能",
    system="你是技术作家。",
    user_template=(
        "用 200 字内总结以下文件的核心功能。\n"
        "文件：`{path}`\n\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.3, max_tokens=600,
)

TASKS["commit"] = RealTask(
    name="commit",
    description="根据 git diff 生成 conventional commit message",
    system="你是一个写 commit message 的专家。遵循 Conventional Commits。",
    user_template=(
        "根据以下 git diff 写一条 commit message。\n\n"
        "格式：\n"
        "<type>(<scope>): <subject>            ← 50 字符以内\n"
        "<空行>\n"
        "<body>                                 ← 72 字符换行\n"
        "<空行>\n"
        "<footer>                               ← BREAKING CHANGE / Closes #\n\n"
        "约束：\n"
        "- type ∈ {feat, fix, refactor, perf, docs, test, chore, style}\n"
        "- subject 用中文或英文皆可，但保持一致\n"
        "- body 说明 *为什么* 而不是 *做了什么*\n\n"
        "diff：\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.2, max_tokens=600,
)

TASKS["translate"] = RealTask(
    name="translate",
    description="把文件中非英文注释翻译成英文，保留代码不变",
    system="你是技术翻译专家。只翻译注释，**绝对不动代码**。",
    user_template=(
        "把以下文件中**所有非英文注释**翻译成英文。\n"
        "文件：`{path}`\n\n"
        "硬性要求：\n"
        "- 只动注释（# // /* */ 等）\n"
        "- 字符串字面量如果显然是面向用户的中文也翻译\n"
        "- 代码标识符、import、关键字保持原样\n"
        "- 输出**完整文件**，不要省略\n\n"
        "```\n{content}\n```\n"
    ),
    temperature=0.2, max_tokens=4096,
)


def get_task(name: str) -> RealTask:
    if name not in TASKS:
        raise KeyError(f"未知任务：{name}，可选：{list(TASKS)}")
    return TASKS[name]


def list_tasks() -> List[str]:
    return list(TASKS.keys())


# ============================================================================
#  Source
# ============================================================================

@dataclass
class Item:
    """一次任务的输入单元。"""
    path: str           # 显示用路径；stdin 时为 "<stdin>"
    content: str        # 喂给模型的文本
    language: str = ""  # 代码语言（python / go / diff / ...）
    meta: dict = field(default_factory=dict)


_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "tsx", ".jsx": "jsx",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".swift": "swift", ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".sh": "bash", ".sql": "sql",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".xml": "xml",
}


def detect_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _EXT_LANG.get(ext, "")


def _safe_read(path: str, max_bytes: int) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    if len(data) > max_bytes:
        data = data[:max_bytes] + f"\n\n... [truncated, file > {max_bytes} bytes] ..."
    return data


class FileSource:
    """单文件 / stdin。path='-' 表示 stdin。"""
    def __init__(self, path: str, max_bytes: int = 200_000):
        self.path = path
        self.max_bytes = max_bytes

    def __iter__(self) -> Iterator[Item]:
        if self.path == "-":
            data = sys.stdin.read()
            if len(data) > self.max_bytes:
                data = data[: self.max_bytes] + "\n... [truncated] ..."
            yield Item(path="<stdin>", content=data, language="")
            return
        content = _safe_read(self.path, self.max_bytes)
        if content is None:
            return
        yield Item(path=self.path, content=content, language=detect_language(self.path))


class GlobSource:
    """glob 模式，支持 `**` 递归。"""
    def __init__(self, pattern: str, max_bytes: int = 200_000, recursive: bool = True):
        self.pattern = pattern
        self.max_bytes = max_bytes
        self.recursive = recursive

    def __iter__(self) -> Iterator[Item]:
        for p in sorted(_glob.glob(self.pattern, recursive=self.recursive)):
            if not os.path.isfile(p):
                continue
            content = _safe_read(p, self.max_bytes)
            if content is None:
                continue
            yield Item(path=p, content=content, language=detect_language(p))


class GitSource:
    """git diff 源。

    mode:
        staged       git diff --cached
        working      git diff
        branch:NAME  git diff NAME...HEAD
        range:SPEC   git diff SPEC
    """
    def __init__(self, mode: str = "staged", ref: str = "HEAD", max_bytes: int = 200_000):
        self.mode = mode
        self.ref = ref
        self.max_bytes = max_bytes

    def _run(self, args: List[str]) -> Optional[str]:
        try:
            r = subprocess.run(
                ["git"] + args, capture_output=True, text=True, encoding="utf-8",
                timeout=30, check=False,
            )
            if r.returncode != 0:
                return None
            return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def __iter__(self) -> Iterator[Item]:
        if self.mode == "staged":
            diff = self._run(["diff", "--cached"])
            label, lang = "staged changes", "diff"
        elif self.mode == "working":
            diff = self._run(["diff"])
            label, lang = "working tree", "diff"
        elif self.mode == "branch":
            diff = self._run(["diff", f"{self.ref}...HEAD"])
            label, lang = f"branch {self.ref}", "diff"
        elif self.mode == "range":
            diff = self._run(["diff", self.ref])
            label, lang = f"range {self.ref}", "diff"
        else:
            return
        if not diff:
            return
        if len(diff) > self.max_bytes:
            diff = diff[: self.max_bytes] + "\n... [truncated] ..."
        yield Item(path=label, content=diff, language=lang)


# ============================================================================
#  工具：把路径变成安全文件名（用于 --out-dir 落盘）
# ============================================================================

def safe_filename(path: str, idx: int, task: str) -> str:
    """src/utils/foo.py → src_utils_foo.py"""
    if path == "<stdin>":
        return f"stdin_{idx}"
    name = path.replace("/", "_").replace("\\", "_").lstrip("._")
    return f"{task}__{name}.md"
