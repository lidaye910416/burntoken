"""Reviewer agent：验证响应的"有意义"程度。

meaningful 模式：检查响应是否跟 prompt 相关
pointless 模式：直接 pass

判定规则（轻量版，不消耗额外 token）：
  - 响应非空
  - 长度 < prompt 的 200 倍（防止模型循环/异常膨胀）
  - 包含 prompt 关键词中的至少 1 个（如果有）
"""
from __future__ import annotations

import re
from typing import Optional

from .strategist import TaskSpec


class Reviewer:
    """轻量级有意义性检查。"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.reviewed = 0
        self.passed = 0
        self.failed = 0

    def check(self, spec: TaskSpec, response_text: str) -> tuple[bool, str]:
        """返回 (passed, reason)。"""
        if not self.enabled:
            self.reviewed += 1
            self.passed += 1
            return True, "reviewer disabled"
        if spec.kind == "pointless":
            self.reviewed += 1
            self.passed += 1
            return True, "pointless mode, skip check"

        self.reviewed += 1
        # 1. 非空
        if not response_text or not response_text.strip():
            self.failed += 1
            return False, "empty response"
        # 2. 长度上限
        if len(response_text) > 50_000:
            self.failed += 1
            return False, f"response too long ({len(response_text)} chars)"
        # 3. 关键词命中
        if spec.user:
            keywords = self._extract_keywords(spec.user)
            if keywords and not any(k in response_text for k in keywords):
                self.failed += 1
                return False, f"response doesn't contain any of keywords: {keywords[:3]}"
        self.passed += 1
        return True, "ok"

    @staticmethod
    def _extract_keywords(prompt: str) -> list[str]:
        """从 prompt 提取 2~10 个中英文关键词。"""
        # 中文 2~4 字短语 + 英文 4+ 字符词
        zh = re.findall(r"[一-龥]{2,6}", prompt)
        en = re.findall(r"[A-Za-z]{4,}", prompt)
        # 去重保序
        seen = set()
        out = []
        for w in zh + en:
            w_low = w.lower()
            if w_low not in seen:
                seen.add(w_low)
                out.append(w)
            if len(out) >= 10:
                break
        return out
