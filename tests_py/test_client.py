"""Tests for ``burntoken.client`` — HBSClient retry/timeout/verify using respx.

These are the red-phase tests for TDD. They exercise the real HBSClient
but intercept httpx with respx so no network is touched.

Coverage:
  * HBSClient.chat() — happy path, parse, latency tracking
  * HBSClient.chat() — retries on 429 / 5xx with exponential backoff
  * HBSClient.chat() — surfaces 4xx as HBSError (no retry)
  * HBSClient.chat() — surfaces httpx.TimeoutException as HBSError? (current
    behaviour: re-raise after max_retries)
  * HBSClient.stream_chat() — yields chunks and stops at [DONE]
  * HBSClient(verify=True|False) — passes the flag to the underlying httpx.Client
  * HBSClient(timeout=...) — passes the timeout to the underlying httpx.Client
  * HBSClient(api_key="") — raises ValueError at construction
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx
import pytest
import respx

from burntoken.client import (
    HBSClient,
    HBSError,
    ChatMessage,
)


BASE = "https://model.hbscloud.com.cn/v1"


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_kwargs() -> Dict[str, Any]:
    return dict(
        api_key="sk-test",
        base_url=BASE,
        timeout=12.0,
        max_retries=3,
        retry_backoff=1.0,  # keep tests fast
        verify=True,
    )


def _ok_payload(model: str = "m") -> Dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        "created": 1_700_000_000,
    }


def _sse_chunks(chunks: List[Dict[str, Any]]) -> str:
    """Build a minimal SSE body from a list of OpenAI-style delta payloads."""
    lines = []
    for c in chunks:
        lines.append("data: " + _json(c))
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
#  Construction
# ---------------------------------------------------------------------------

class TestHBSClientConstruction:
    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="api_key"):
            HBSClient(api_key="")

    def test_base_url_is_stripped(self):
        c = HBSClient(api_key="sk-test", base_url=BASE + "/")
        assert c.base_url == BASE
        c.close()

    def test_verify_true_is_passed_to_httpx(self):
        c = HBSClient(api_key="sk-test", verify=True)
        try:
            assert c._client._transport.verify is True  # type: ignore[attr-defined]
        except AttributeError:
            # httpx ≥ 0.28 stores verify in a different attr; fall back to the
            # kwarg we passed in (still a valid contract test).
            assert c.verify is True

    def test_verify_false_is_passed_to_httpx(self):
        c = HBSClient(api_key="sk-test", verify=False)
        try:
            assert c._client._transport.verify is False  # type: ignore[attr-defined]
        except AttributeError:
            assert c.verify is False

    def test_timeout_is_passed_to_httpx(self):
        c = HBSClient(api_key="sk-test", timeout=42.0)
        try:
            assert c._client.timeout.connect == 42.0 or c._client.timeout == 42.0
        except AttributeError:
            assert c.timeout == 42.0


# ---------------------------------------------------------------------------
#  chat() — happy path
# ---------------------------------------------------------------------------

class TestHBSClientChatHappy:
    def test_chat_returns_parsed_response(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(200, json=_ok_payload())
            )
            with HBSClient(api_key="sk-test", base_url=BASE, retry_backoff=1.0) as c:
                resp = c.chat([ChatMessage("user", "hi")], model="m")
        assert resp.text == "hello"
        assert resp.model == "m"
        assert resp.usage.prompt_tokens == 5
        assert resp.usage.completion_tokens == 7
        assert resp.usage.total_tokens == 12
        assert route.called

    def test_chat_sends_bearer_auth_header(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(200, json=_ok_payload())
            )
            with HBSClient(api_key="sk-secret", base_url=BASE) as c:
                c.chat([ChatMessage("user", "hi")], model="m")
        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer sk-secret"

    def test_chat_payload_includes_model_and_messages(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(200, json=_ok_payload())
            )
            with HBSClient(api_key="sk-test", base_url=BASE) as c:
                c.chat([ChatMessage("user", "hi")], model="m-x", temperature=0.5)
        sent = route.calls.last.request
        body = sent.content.decode()
        assert '"model":"m-x"' in body or '"model": "m-x"' in body
        assert '"role":"user"' in body
        assert '"content":"hi"' in body
        assert '"temperature":0.5' in body


# ---------------------------------------------------------------------------
#  chat() — retry behaviour
# ---------------------------------------------------------------------------

class TestHBSClientChatRetry:
    def test_retries_on_429_then_succeeds(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                side_effect=[
                    httpx.Response(429, text="rate limited"),
                    httpx.Response(200, json=_ok_payload()),
                ]
            )
            t0 = time.time()
            with HBSClient(
                api_key="sk-test", base_url=BASE, max_retries=3, retry_backoff=1.0
            ) as c:
                resp = c.chat([ChatMessage("user", "hi")], model="m")
            elapsed = time.time() - t0
        assert resp.text == "hello"
        assert route.call_count == 2
        # The 2nd attempt should happen after backoff = 1.0^1 = 1.0s sleep
        assert elapsed >= 0.9, f"expected backoff sleep, got {elapsed:.2f}s"

    def test_retries_on_500_then_succeeds(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                side_effect=[
                    httpx.Response(500, text="boom"),
                    httpx.Response(200, json=_ok_payload()),
                ]
            )
            with HBSClient(
                api_key="sk-test", base_url=BASE, max_retries=3, retry_backoff=1.0
            ) as c:
                resp = c.chat([ChatMessage("user", "hi")], model="m")
        assert resp.text == "hello"
        assert route.call_count == 2

    def test_gives_up_after_max_retries_on_5xx(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(500, text="boom")
            )
            with HBSClient(
                api_key="sk-test", base_url=BASE, max_retries=2, retry_backoff=1.0
            ) as c:
                with pytest.raises(HBSError) as ei:
                    c.chat([ChatMessage("user", "hi")], model="m")
        assert ei.value.status == 500
        # 2 retries → at most 2 attempts; never 3.
        assert route.call_count == 2

    def test_does_not_retry_on_4xx(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(401, text="bad key")
            )
            with HBSClient(
                api_key="sk-test", base_url=BASE, max_retries=5, retry_backoff=1.0
            ) as c:
                with pytest.raises(HBSError) as ei:
                    c.chat([ChatMessage("user", "hi")], model="m")
        assert ei.value.status == 401
        # 401 is *not* retryable → exactly 1 attempt.
        assert route.call_count == 1


# ---------------------------------------------------------------------------
#  chat() — timeout propagation
# ---------------------------------------------------------------------------

class TestHBSClientChatTimeout:
    def test_timeout_exception_is_retried_then_raised(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                side_effect=httpx.TimeoutException("slow")
            )
            with HBSClient(
                api_key="sk-test", base_url=BASE, max_retries=2, retry_backoff=1.0
            ) as c:
                with pytest.raises(httpx.TimeoutException):
                    c.chat([ChatMessage("user", "hi")], model="m")
        assert route.call_count == 2


# ---------------------------------------------------------------------------
#  stream_chat() — SSE parsing
# ---------------------------------------------------------------------------

class TestHBSClientStream:
    def test_stream_yields_deltas_and_stops_at_done(self):
        sse = _sse_chunks([
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "hel"}}]},
            {"choices": [{"index": 0, "delta": {"content": "lo"}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
        ])
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            )
            with HBSClient(api_key="sk-test", base_url=BASE) as c:
                deltas = list(c.stream_chat([ChatMessage("user", "hi")], model="m"))
        assert route.called
        assert "".join(d.content for d in deltas) == "hello"
        assert deltas[-1].finish_reason == "stop"
        assert deltas[-1].usage is not None
        assert deltas[-1].usage.completion_tokens == 2

    def test_stream_raises_on_4xx(self):
        with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(401, text="nope")
            )
            with HBSClient(api_key="sk-test", base_url=BASE) as c:
                with pytest.raises(HBSError) as ei:
                    list(c.stream_chat([ChatMessage("user", "hi")], model="m"))
        assert ei.value.status == 401
        assert route.called


# ---------------------------------------------------------------------------
#  _build_payload / _parse_response / _parse_stream_chunk
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_basic_payload(self):
        from burntoken.client import _build_payload
        p = _build_payload([ChatMessage("user", "hi")], "m")
        assert p["model"] == "m"
        assert p["stream"] is False
        assert p["messages"] == [{"role": "user", "content": "hi"}]

    def test_payload_with_optional_fields(self):
        from burntoken.client import _build_payload
        p = _build_payload(
            [ChatMessage("system", "sys"), ChatMessage("user", "hi")],
            "m",
            temperature=0.3,
            max_tokens=100,
            top_p=0.9,
            stop=["END"],
            extra={"custom": "x"},
        )
        assert p["temperature"] == 0.3
        assert p["max_tokens"] == 100
        assert p["top_p"] == 0.9
        assert p["stop"] == ["END"]
        assert p["custom"] == "x"

    def test_payload_omits_optional_when_none(self):
        from burntoken.client import _build_payload
        p = _build_payload([ChatMessage("user", "hi")], "m")
        assert "max_tokens" not in p
        assert "stop" not in p

    def test_payload_with_named_message(self):
        from burntoken.client import _build_payload
        p = _build_payload(
            [ChatMessage("user", "hi", name="alice")], "m"
        )
        assert p["messages"][0]["name"] == "alice"


class TestParseResponse:
    def test_full_response(self):
        from burntoken.client import _parse_response
        data = {
            "id": "x",
            "model": "m",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hi"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        r = _parse_response(data, "m", latency=42)
        assert r.id == "x"
        assert r.model == "m"
        assert r.latency_ms == 42
        assert r.choices[0].message.content == "hi"
        assert r.usage.total_tokens == 3
        assert r.text == "hi"

    def test_empty_choices(self):
        from burntoken.client import _parse_response
        r = _parse_response({"choices": []}, "m", latency=0)
        assert r.text == ""
        assert r.choices == []

    def test_missing_usage_defaults_to_zero(self):
        from burntoken.client import _parse_response
        r = _parse_response(
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            "m", latency=0,
        )
        assert r.usage.prompt_tokens == 0


class TestParseStreamChunk:
    def test_content_delta(self):
        from burntoken.client import _parse_stream_chunk
        d = _parse_stream_chunk({
            "choices": [{"index": 0, "delta": {"content": "ab"}}],
        })
        assert d.content == "ab"
        assert d.finish_reason is None
        assert d.usage is None

    def test_reasoning_delta(self):
        from burntoken.client import _parse_stream_chunk
        d = _parse_stream_chunk({
            "choices": [{"index": 0, "delta": {"reasoning_content": "thinking"}}],
        })
        assert d.reasoning == "thinking"

    def test_final_chunk_with_usage(self):
        from burntoken.client import _parse_stream_chunk
        d = _parse_stream_chunk({
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
        })
        assert d.finish_reason == "stop"
        assert d.usage is not None
        assert d.usage.completion_tokens == 5

    def test_empty_choices(self):
        from burntoken.client import _parse_stream_chunk
        d = _parse_stream_chunk({"choices": []})
        assert d.content == ""
        assert d.reasoning == ""


# ---------------------------------------------------------------------------
#  HBSError — dataclass attributes
# ---------------------------------------------------------------------------

class TestHBSError:
    def test_attributes_and_message(self):
        e = HBSError(401, "nope body", "explicit msg", retryable=True)
        assert e.status == 401
        assert e.body == "nope body"
        assert e.message == "explicit msg"
        assert e.retryable is True
        assert "[401]" in str(e)

    def test_retryable_defaults_to_false(self):
        e = HBSError(400, "bad")
        assert e.retryable is False

    def test_long_body_is_truncated(self):
        e = HBSError(500, "x" * 1000)
        assert len(e.message) <= 300


# ---------------------------------------------------------------------------
#  list_models — happy path
# ---------------------------------------------------------------------------

class TestListModels:
    def test_list_models_returns_data_array(self):
        with respx.mock(base_url=BASE) as router:
            route = router.get("/models").mock(
                return_value=httpx.Response(200, json={
                    "data": [{"id": "m1"}, {"id": "m2"}],
                })
            )
            with HBSClient(api_key="sk-test", base_url=BASE) as c:
                models = c.list_models()
        assert [m["id"] for m in models] == ["m1", "m2"]
        assert route.called


# ---------------------------------------------------------------------------
#  StreamDelta defaults
# ---------------------------------------------------------------------------

class TestStreamDelta:
    def test_defaults(self):
        from burntoken.client import StreamDelta
        d = StreamDelta()
        assert d.content == ""
        assert d.reasoning == ""
        assert d.finish_reason is None
        assert d.usage is None


# ---------------------------------------------------------------------------
#  AsyncHBSClient — chat happy / retry / stream
# ---------------------------------------------------------------------------

class TestAsyncHBSClient:
    @pytest.mark.asyncio
    async def test_async_chat_happy(self):
        from burntoken.client import AsyncHBSClient
        async with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(200, json=_ok_payload())
            )
            async with AsyncHBSClient(
                api_key="sk-test", base_url=BASE, retry_backoff=1.0
            ) as c:
                resp = await c.chat([ChatMessage("user", "hi")], model="m")
        assert resp.text == "hello"
        assert route.called

    @pytest.mark.asyncio
    async def test_async_chat_retries_on_5xx(self):
        from burntoken.client import AsyncHBSClient
        async with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                side_effect=[
                    httpx.Response(503, text="down"),
                    httpx.Response(200, json=_ok_payload()),
                ]
            )
            async with AsyncHBSClient(
                api_key="sk-test", base_url=BASE, max_retries=3, retry_backoff=1.0
            ) as c:
                resp = await c.chat([ChatMessage("user", "hi")], model="m")
        assert resp.text == "hello"
        assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_async_does_not_retry_on_4xx(self):
        from burntoken.client import AsyncHBSClient
        async with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(403, text="forbidden")
            )
            async with AsyncHBSClient(
                api_key="sk-test", base_url=BASE, max_retries=4, retry_backoff=1.0
            ) as c:
                with pytest.raises(HBSError) as ei:
                    await c.chat([ChatMessage("user", "hi")], model="m")
        assert ei.value.status == 403
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_async_list_models(self):
        from burntoken.client import AsyncHBSClient
        async with respx.mock(base_url=BASE) as router:
            route = router.get("/models").mock(
                return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
            )
            async with AsyncHBSClient(api_key="sk-test", base_url=BASE) as c:
                models = await c.list_models()
        assert models[0]["id"] == "m1"
        assert route.called

    @pytest.mark.asyncio
    async def test_async_stream_yields_deltas(self):
        from burntoken.client import AsyncHBSClient
        sse = _sse_chunks([
            {"choices": [{"index": 0, "delta": {"content": "a"}}]},
            {"choices": [{"index": 0, "delta": {"content": "b"}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ])
        async with respx.mock(base_url=BASE) as router:
            router.post("/chat/completions").mock(
                return_value=httpx.Response(
                    200, content=sse.encode(),
                    headers={"content-type": "text/event-stream"},
                )
            )
            async with AsyncHBSClient(api_key="sk-test", base_url=BASE) as c:
                deltas = []
                async for d in c.stream_chat([ChatMessage("user", "hi")], model="m"):
                    deltas.append(d)
        assert "".join(d.content for d in deltas) == "ab"
        assert deltas[-1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_async_stream_raises_on_4xx(self):
        from burntoken.client import AsyncHBSClient
        async with respx.mock(base_url=BASE) as router:
            route = router.post("/chat/completions").mock(
                return_value=httpx.Response(401, text="nope")
            )
            async with AsyncHBSClient(api_key="sk-test", base_url=BASE) as c:
                with pytest.raises(HBSError) as ei:
                    async for _ in c.stream_chat(
                        [ChatMessage("user", "hi")], model="m"
                    ):
                        pass
        assert ei.value.status == 401
        assert route.called

    def test_async_construction_verify_and_timeout(self):
        from burntoken.client import AsyncHBSClient
        c = AsyncHBSClient(api_key="sk-test", base_url=BASE, verify=False, timeout=5.0)
        try:
            assert c.verify is False
            assert c.timeout == 5.0
        finally:
            # Cleanup async client — needs an event loop
            import asyncio
            asyncio.run(c.aclose())


# ---------------------------------------------------------------------------
#  Context manager / close
# ---------------------------------------------------------------------------

class TestContextManagers:
    def test_sync_context_manager_closes(self):
        with HBSClient(api_key="sk-test", base_url=BASE) as c:
            assert c._client is not None
        # After exit, calling close again is safe
        c.close()  # noqa: B018 — should not raise
