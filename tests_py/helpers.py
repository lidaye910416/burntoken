"""薄壳 invoke helper —— 直接复用 burntoken.cli.main。

设计目标：
- 不引入子进程（保持测试 < 5s 跑完）
- 不依赖网络（所有副作用通过 monkeypatch 注入）
- 对 argparse 的 --version 走 SystemExit(0) 路径
"""
from __future__ import annotations

import contextlib
import io
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class InvokeResult:
    """cli.main() 的运行快照。"""
    exit_code: int
    stdout: str
    stderr: str

    def assert_ok(self) -> "InvokeResult":
        assert self.exit_code == 0, (
            f"expected exit 0, got {self.exit_code}\n"
            f"--- stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )
        return self

    def assert_exit(self, code: int) -> "InvokeResult":
        assert self.exit_code == code, (
            f"expected exit {code}, got {self.exit_code}\n"
            f"--- stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )
        return self


def invoke(argv: List[str]) -> InvokeResult:
    """直接调 burntoken.cli.main(argv)，捕获 stdout/stderr 和退出码。

    argparse 的 --version / --help 是通过 SystemExit 实现的，
    我们要把它转成正常的 exit_code。
    """
    # 延迟导入：避免 conftest 之外的环境污染
    from burntoken import cli

    out, err = io.StringIO(), io.StringIO()
    exit_code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        # cli.main() 直接返回 int；不要丢。SystemExit 仍走 except 分支。
        if isinstance(rc, int):
            exit_code = rc
    except SystemExit as e:
        # argparse 的 action="version" / "help" 走 SystemExit(code)
        code = e.code
        exit_code = 0 if code is None else int(code)
    except BaseException as e:  # noqa: BLE001
        # 业务异常：不期望发生 —— 透传到测试断言里
        err.write(f"UNCAUGHT: {type(e).__name__}: {e}")
        exit_code = 99

    return InvokeResult(
        exit_code=exit_code,
        stdout=out.getvalue(),
        stderr=err.getvalue(),
    )


@contextlib.contextmanager
def env(**overrides):
    """临时设置/取消环境变量；退出时还原。"""
    saved = {k: os.environ.get(k) for k in overrides}
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# 延迟导入 os 以避免顶层循环
import os  # noqa: E402
