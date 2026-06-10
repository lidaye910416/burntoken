"""pytest 全局 fixtures for tests_py/.

约定:
  - 不读 ~/.config/burntoken/ 真实配置
  - 不打真实网络
  - 所有 env 注入用 monkeypatch + tmp .env,保证测试可重入
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest


# Make the burntoken package importable when running `pytest` from project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ----------------------------- pytest-asyncio 模式 -----------------------------
# pyproject.toml [tool.pytest.ini_options] 里设置了 asyncio_mode=auto。
# 这里给出显式 marker,方便在某些 case 里手写 `@pytest.mark.asyncio`。


# ----------------------------- 临时 .env fixture -----------------------------

@pytest.fixture
def tmp_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """在 tmp_path 下建一个最小可用 .env,并把 cwd 切过去,让 load_env_fallback() 找得到。

    写入的 key 都是占位,不会触发真实网络。 测试若需要自定义 key,用 monkeypatch.setenv() 即可。
    """
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# 测试用 .env (临时)\n"
        "HBS_API_KEY=sk-test-placeholder\n"
        "BURNTOKEN_CONFIG=\n",
        encoding="utf-8",
    )
    # 隔离:把 cwd 切到 tmp_path,这样 load_env_fallback() 找的是这个 .env
    monkeypatch.chdir(tmp_path)
    # 关键:在 load_env_fallback 之前清掉这些 env,避免和真值混淆
    for k in ("HBS_API_KEY", "HBS_BASE_URL", "BURNTOKEN_CONFIG", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(k, raising=False)
    yield env_path


# ----------------------------- 临时日志路径 fixture -----------------------------

@pytest.fixture
def tmp_log_file(tmp_path: Path) -> str:
    """Path to a fresh JSONL log file inside a tmp dir."""
    return str(tmp_path / "events.jsonl")


# ----------------------------- httpx 拦截 fixture -----------------------------

class _FakeAsyncClient:
    """最小可用的 httpx.AsyncClient 替身,所有方法/属性返回已预设的值。"""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.requests: list[dict] = []

    async def get(self, url, **kw):
        from unittest.mock import AsyncMock
        m = AsyncMock()
        m.json.return_value = {"data": []}
        m.raise_for_status.return_value = None
        m.status_code = 200
        m.text = ""
        self.requests.append({"method": "GET", "url": url, **kw})
        return m

    async def post(self, url, **kw):
        from unittest.mock import AsyncMock
        m = AsyncMock()
        m.json.return_value = {"id": "x", "model": "m", "choices": [], "usage": {}}
        m.raise_for_status.return_value = None
        m.status_code = 200
        m.text = ""
        self.requests.append({"method": "POST", "url": url, **kw})
        return m

    async def aclose(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    def stream(self, *a, **kw):
        from contextlib import contextmanager
        @contextmanager
        def _cm():
            from unittest.mock import MagicMock
            resp = MagicMock()
            resp.status_code = 200
            async def _aiter():
                if False:
                    yield  # 空迭代
            resp.aiter_lines = _aiter
            yield resp
        return _cm()


class _FakeSyncClient:
    """最小可用的 httpx.Client 替身,所有方法/属性返回已预设的值。"""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.requests: list[dict] = []

    def get(self, url, **kw):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.json.return_value = {"data": []}
        m.raise_for_status.return_value = None
        m.status_code = 200
        m.text = ""
        self.requests.append({"method": "GET", "url": url, **kw})
        return m

    def post(self, url, **kw):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.json.return_value = {"id": "x", "model": "m", "choices": [], "usage": {}}
        m.raise_for_status.return_value = None
        m.status_code = 200
        m.text = ""
        self.requests.append({"method": "POST", "url": url, **kw})
        return m

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def stream(self, *a, **kw):
        from contextlib import contextmanager
        @contextmanager
        def _cm():
            from unittest.mock import MagicMock
            resp = MagicMock()
            resp.status_code = 200
            resp.iter_lines = lambda: iter([])
            yield resp
        return _cm()


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch httpx.Client / httpx.AsyncClient 为 fake,不打真实网络。

    返回 (FakeSyncClient, FakeAsyncClient) 引用,测试可检查 .requests。
    """
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeSyncClient, raising=True)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient, raising=True)
    return _FakeSyncClient, _FakeAsyncClient
