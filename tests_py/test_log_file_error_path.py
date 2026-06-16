"""Regression test for --log-file not writing JSONL on non-HBSError failures.

Bug: cmd_run's `except HBSError` only caught HBSClient's custom error class.
When the underlying httpx call raised (ConnectError, TimeoutException, etc.),
the exception bypassed the except, hit the `finally` block which closed the
log sink, and the tracker never recorded the failure. Net result: the JSONL
file existed (was opened in append mode by LogEventSink) but stayed empty
even when --log-file was specified.

Fix: broaden the except in cmd_run so any Exception during the API call is
recorded as a failed run in the tracker (which then emits to the JSONL sink).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

from tests_py.helpers import invoke


HBS_BASE = "http://127.0.0.1:1"  # blackhole: instant ConnectError


@pytest.fixture
def log_path(tmp_path: Path) -> str:
    return str(tmp_path / "burn.jsonl")


@pytest.fixture
def env_setup(monkeypatch: pytest.MonkeyPatch):
    """Force a deterministic, non-network HBS_BASE_URL so every test starts clean."""
    monkeypatch.setenv("HBS_API_KEY", "sk-test-fake")
    monkeypatch.setenv("HBS_BASE_URL", HBS_BASE)
    monkeypatch.delenv("HBS_MODEL", raising=False)


def test_log_file_writes_event_on_connection_error(
    env_setup, log_path: str
):
    """The bug repro: ConnectError on the API call must still produce a JSONL line."""
    with respx.mock(base_url=HBS_BASE) as router:
        router.post("/chat/completions").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = invoke(["--log-file", log_path, "-p", "ping"])

    # The CLI exits non-zero (network failure) — we don't care which code,
    # only that the JSONL was written.
    assert result.exit_code != 0, (
        f"expected non-zero exit on ConnectError, got 0\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    # The bug: file was never created. The fix: file exists with at least one line.
    assert os.path.exists(log_path), (
        f"--log-file {log_path} was not created on a failed call.\n"
        f"This is the bug: tracker.record(ok=False) is not invoked when the\n"
        f"underlying httpx raises a non-HBSError exception, so the JSONL sink\n"
        f"is opened but never written to before close().\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    lines = [json.loads(l) for l in Path(log_path).read_text().splitlines() if l.strip()]
    assert lines, "JSONL file exists but is empty"
    last = lines[-1]
    assert last["level"] == "error", f"expected level=error, got {last['level']}: {last}"
    assert last["event"] == "run", f"expected event=run, got {last['event']}: {last}"
    assert last["error"], f"expected non-empty error field, got {last!r}"
    assert last["tokens"]["prompt"] == 0
    assert last["tokens"]["completion"] == 0
