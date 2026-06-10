"""Tests for burntoken.tracker — token/cost accumulation, JSONL emission, append-on-resume."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from burntoken.tracker import (
    LogEventSink,
    RunStats,
    TokenPricing,
    TokenTracker,
)


# ---------- TokenPricing ----------

def test_token_pricing_default_is_zero():
    p = TokenPricing()
    assert p.prompt_per_1k == 0.0
    assert p.completion_per_1k == 0.0
    assert p.cost(1234, 5678) == 0.0


def test_token_pricing_cost_formula():
    p = TokenPricing(prompt_per_1k=0.01, completion_per_1k=0.03)
    # 1000 prompt tokens * 0.01 + 2000 completion * 0.03 = 0.01 + 0.06 = 0.07
    assert p.cost(1000, 2000) == pytest.approx(0.07)


def test_token_pricing_fractional_tokens():
    p = TokenPricing(prompt_per_1k=1.0, completion_per_1k=2.0)
    # 500 prompt * 1.0 + 250 completion * 2.0 = 0.5 + 0.5 = 1.0
    assert p.cost(500, 250) == pytest.approx(1.0)


# ---------- TokenTracker accumulation ----------

def test_tracker_starts_at_zero():
    t = TokenTracker()
    s = t.summary()
    assert s["requests"] == 0
    assert s["ok"] == 0
    assert s["failed"] == 0
    assert s["prompt_tokens"] == 0
    assert s["completion_tokens"] == 0
    assert s["total_tokens"] == 0
    assert s["cost"] == 0.0


def test_tracker_accumulates_tokens_and_requests():
    t = TokenTracker(TokenPricing(prompt_per_1k=0.001, completion_per_1k=0.002))
    t.record(prompt=100, completion=50, latency_ms=200, ok=True)
    t.record(prompt=200, completion=80, latency_ms=300, ok=True)
    s = t.summary()
    assert s["requests"] == 2
    assert s["ok"] == 2
    assert s["failed"] == 0
    assert s["prompt_tokens"] == 300
    assert s["completion_tokens"] == 130
    assert s["total_tokens"] == 430
    # 300/1000*0.001 + 130/1000*0.002 = 0.0003 + 0.00026 = 0.00056
    assert s["cost"] == pytest.approx(0.00056, rel=1e-6)


def test_tracker_separates_ok_and_failed_counts():
    t = TokenTracker()
    t.record(10, 20, 100, ok=True)
    t.record(11, 21, 200, ok=True)
    t.record(12, 22, 300, ok=False, error="boom")
    s = t.summary()
    assert s["requests"] == 3
    assert s["ok"] == 2
    assert s["failed"] == 1


def test_tracker_failed_request_still_counts_tokens():
    """Even failed calls may have consumed tokens (rate limit / network drop
    after sending). The tracker must still accumulate the token counts."""
    t = TokenTracker()
    t.record(prompt=999, completion=0, latency_ms=5000, ok=False, error="net")
    assert t.prompt_tokens == 999
    assert t.requests_failed == 1


def test_tracker_latency_max_and_sum():
    t = TokenTracker()
    t.record(1, 1, 100, ok=True)
    t.record(1, 1, 500, ok=True)
    t.record(1, 1, 250, ok=True)
    assert t.latency_max_ms == 500
    assert t.latency_sum_ms == 850
    assert t.avg_latency_ms == pytest.approx(850 / 3)


def test_tracker_avg_latency_zero_when_no_requests():
    t = TokenTracker()
    assert t.avg_latency_ms == 0.0


def test_tracker_history_returns_copy():
    t = TokenTracker()
    t.record(1, 1, 1, ok=True)
    t.record(2, 2, 2, ok=False, error="x")
    h = t.history()
    assert len(h) == 2
    assert all(isinstance(s, RunStats) for s in h)
    # Mutating the returned list must not affect the tracker.
    h.clear()
    assert len(t.history()) == 2


def test_tracker_cost_property_matches_pricing():
    pricing = TokenPricing(prompt_per_1k=0.5, completion_per_1k=1.5)
    t = TokenTracker(pricing)
    t.record(1000, 1000, 100, ok=True)
    # 0.5 + 1.5 = 2.0
    assert t.cost == pytest.approx(2.0)


def test_tracker_tps_and_rps():
    t = TokenTracker()
    t.record(10, 20, 10, ok=True)
    t.record(10, 30, 10, ok=True)
    # Force elapsed to a known value by sleeping briefly.
    time.sleep(0.05)
    assert t.rps > 0
    assert t.tps > 0


# ---------- over_budget ----------

def test_over_budget_returns_none_when_within_limits():
    t = TokenTracker()
    t.record(100, 50, 10, ok=True)
    assert t.over_budget(max_tokens=10_000, max_cost=10.0) is None


def test_over_budget_triggers_on_tokens():
    t = TokenTracker()
    t.record(300, 200, 10, ok=True)  # total = 500, under 1000
    assert t.over_budget(max_tokens=1000, max_cost=None) is None
    t.record(500, 100, 10, ok=True)  # total now 1100, over 1000
    reason = t.over_budget(max_tokens=1000, max_cost=None)
    assert reason is not None
    assert "tokens" in reason


def test_over_budget_triggers_on_cost():
    t = TokenTracker(TokenPricing(prompt_per_1k=1.0, completion_per_1k=1.0))
    t.record(500, 500, 10, ok=True)  # cost = 1.0
    assert t.over_budget(max_tokens=None, max_cost=2.0) is None
    t.record(1000, 1000, 10, ok=True)  # cost = 2.0
    reason = t.over_budget(max_tokens=None, max_cost=2.0)
    assert reason is not None
    assert "cost" in reason


# ---------- thread-safety smoke ----------

def test_tracker_concurrent_records_preserve_totals():
    t = TokenTracker()

    def worker(n: int):
        for i in range(n):
            t.record(prompt=1, completion=1, latency_ms=1, ok=True)

    threads = [threading.Thread(target=worker, args=(200,)) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    s = t.summary()
    assert s["requests"] == 8 * 200
    assert s["prompt_tokens"] == 8 * 200
    assert s["completion_tokens"] == 8 * 200
    assert s["total_tokens"] == 8 * 400


# ---------- LogEventSink: JSONL emission ----------

def test_sink_creates_parent_directory(tmp_path: Path):
    nested = tmp_path / "a" / "b" / "c" / "events.jsonl"
    sink = LogEventSink(str(nested))
    try:
        sink.emit(event="x")
    finally:
        sink.close()
    assert nested.exists()


def test_sink_emits_valid_jsonl_one_line_per_event(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    try:
        sink.set_context(model="gpt-x", prompt="hello")
        sink.emit(event="run", prompt_tokens=10, completion_tokens=20, latency_ms=100)
        sink.emit(event="run", prompt_tokens=30, completion_tokens=40, latency_ms=200)
    finally:
        sink.close()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 2

    for line in lines:
        obj = json.loads(line)  # must be valid JSON
        assert obj["event"] == "run"
        assert "timestamp" in obj
        assert "run_id" in obj
        assert obj["model"] == "gpt-x"
        assert obj["prompt"] == "hello"
        assert "tokens" in obj
        assert obj["tokens"]["total"] == obj["tokens"]["prompt"] + obj["tokens"]["completion"]


def test_sink_emit_includes_provided_token_counts(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    try:
        sink.emit(event="run", prompt_tokens=12, completion_tokens=34, latency_ms=56)
    finally:
        sink.close()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        obj = json.loads(f.readline())
    assert obj["tokens"]["prompt"] == 12
    assert obj["tokens"]["completion"] == 34
    assert obj["tokens"]["total"] == 46
    assert obj["latency_ms"] == 56


def test_sink_emit_includes_error_and_level(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    try:
        sink.emit(event="run", level="error", error="kaboom")
    finally:
        sink.close()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        obj = json.loads(f.readline())
    assert obj["level"] == "error"
    assert obj["error"] == "kaboom"


def test_sink_emit_accepts_extra_kwargs(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    try:
        sink.emit(event="run", custom_field="hello", n=42)
    finally:
        sink.close()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        obj = json.loads(f.readline())
    assert obj["custom_field"] == "hello"
    assert obj["n"] == 42


def test_sink_close_is_idempotent(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    sink.close()
    # Second close must not raise.
    sink.close()


# ---------- LogEventSink: append-on-resume ----------

def test_sink_appends_on_resume_same_path(tmp_path: Path):
    """Opening LogEventSink twice at the same path must append, not truncate.

    This models: a long-running run gets interrupted; user runs `burntoken
    burn --log-file events.jsonl` again, and the new events should append to
    the existing log.
    """
    path = str(tmp_path / "resume.jsonl")

    # First "session"
    s1 = LogEventSink(path)
    s1.set_context(model="m1", prompt="p1")
    s1.emit(event="run", prompt_tokens=10, completion_tokens=20, latency_ms=100)
    s1.close()

    # Second "session" — same path
    s2 = LogEventSink(path)
    try:
        s2.set_context(model="m2", prompt="p2")
        s2.emit(event="run", prompt_tokens=30, completion_tokens=40, latency_ms=200)
    finally:
        s2.close()

    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 2

    first, second = (json.loads(ln) for ln in lines)
    assert first["model"] == "m1"
    assert first["tokens"]["prompt"] == 10
    assert second["model"] == "m2"
    assert second["tokens"]["prompt"] == 30
    # run_id may differ between sessions (sink generates one if not given) —
    # both should be present and non-empty.
    assert first["run_id"] and second["run_id"]


def test_sink_appends_with_explicit_run_id_preserved_across_resume(tmp_path: Path):
    path = str(tmp_path / "resume2.jsonl")
    rid = "fixed-run-id-abc"

    s1 = LogEventSink(path, run_id=rid)
    s1.emit(event="run", prompt_tokens=1, completion_tokens=2, latency_ms=10)
    s1.close()

    s2 = LogEventSink(path, run_id=rid)
    try:
        s2.emit(event="run", prompt_tokens=3, completion_tokens=4, latency_ms=20)
    finally:
        s2.close()

    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert obj["run_id"] == rid


def test_sink_unicode_in_prompt_is_preserved(tmp_log_file: str):
    sink = LogEventSink(tmp_log_file)
    try:
        sink.set_context(prompt="你好，种子是 42")
        sink.emit(event="run")
    finally:
        sink.close()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        raw = f.read()
    assert "你好，种子是 42" in raw
    obj = json.loads(raw.splitlines()[0])
    assert obj["prompt"] == "你好，种子是 42"


# ---------- TokenTracker + LogEventSink integration ----------

def test_tracker_emits_one_jsonl_per_record(tmp_log_file: str):
    pricing = TokenPricing(prompt_per_1k=0.01, completion_per_1k=0.02)
    tracker = TokenTracker(pricing)
    sink = LogEventSink(tmp_log_file)
    tracker.attach_log(sink)
    try:
        tracker.record(prompt=100, completion=50, latency_ms=200, ok=True)
        tracker.record(prompt=200, completion=80, latency_ms=300, ok=False, error="e")
    finally:
        tracker.close_log()

    with open(tmp_log_file, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 2

    first, second = (json.loads(ln) for ln in lines)
    assert first["level"] == "info"
    assert first["tokens"]["prompt"] == 100
    assert first["tokens"]["completion"] == 50
    # cost_usd = 100/1000*0.01 + 50/1000*0.02 = 0.001 + 0.001 = 0.002
    assert first["cost_usd"] == pytest.approx(0.002, rel=1e-6)

    assert second["level"] == "error"
    assert second["error"] == "e"


def test_tracker_emit_continues_after_resume(tmp_path: Path):
    """Combine the two hard rules: tracker accumulates correctly across a
    resume, AND the JSONL log appended by LogEventSink contains both runs."""
    path = str(tmp_path / "events.jsonl")
    pricing = TokenPricing(prompt_per_1k=0.001, completion_per_1k=0.002)

    # Run 1
    t1 = TokenTracker(pricing)
    s1 = LogEventSink(path)
    t1.attach_log(s1)
    t1.record(100, 50, 10, ok=True)
    t1.record(100, 50, 10, ok=True)
    t1.close_log()

    # Run 2 — fresh tracker, but same log file path => must append.
    t2 = TokenTracker(pricing)
    s2 = LogEventSink(path)
    t2.attach_log(s2)
    t2.record(100, 50, 10, ok=True)
    t2.close_log()

    # Token accumulation is per-tracker instance, but the log should now have
    # 3 lines.
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert obj["tokens"]["total"] == 150
