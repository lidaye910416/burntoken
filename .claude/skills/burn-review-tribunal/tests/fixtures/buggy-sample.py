# .claude/skills/burn-review-tribunal/tests/fixtures/buggy-sample.py
"""A tiny sample file with multiple intentional issues for tribunal testing."""

import os
import random
import subprocess


def process_user_path(path):
    # Security: path traversal + shell injection
    cmd = f"cat {path}"
    return os.popen(cmd).read()


def divide(a, b):
    # Correctness: division by zero
    return a / b


class Cache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        # Correctness: KeyError on missing key
        return self.data[key]

    def get_or_default(self, key, default=None):
        # Performance: double dict access
        if key in self.data:
            return self.data[key]
        return default


def slow_search(items, target):
    # Performance: O(n^2) instead of set lookup
    found = []
    for item in items:
        if target in item:  # also O(n) per item
            found.append(item)
    return found


def magic_numbers(x):
    # Style: magic number
    if x > 42:
        return x * 3.14159
    return x


def undocumented_function(a, b):
    # Docs: no docstring
    return a + b


def flaky_random():
    # Testability: random not injectable
    return random.random() < 0.5
