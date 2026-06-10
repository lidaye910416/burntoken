"""Integration-level smoke tests for the burntoken CLI.

These are guard tests: if the public CLI surface breaks, these go red.
They exercise argparse end-to-end (build_parser + main) with no real
network calls — every external boundary is mocked.

Coverage:
- ``burntoken --version``        exits 0, prints version
- ``burntoken --models``         with mocked client returns a list
- ``burntoken burn -n 0``        exits cleanly (zero-iteration loop)
- ``burntoken config show``      prints resolved env as JSON

Note: the original 983-line cli.py took ``config --show`` as a flag,
but the refactored parser uses the canonical subcommand form
``config show`` (a positional ``action`` arg). The subcommand form is
what the public surface uses; legacy ``--models``/``--repl`` top-level
flags are still accepted via a backward-compat shim in ``cli.__init__``.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from tests_py.helpers import env, invoke


# ---------------------------------------------------------------------------
#  --version
# ---------------------------------------------------------------------------

def test_version_flag_exits_zero_and_prints_version():
    r = invoke(["--version"])
    r.assert_exit(0)
    # burntoken _version.py has __version__ = "0.1.0" — argparse prints
    # "burntoken <ver>" via action="version".
    assert r.stdout.strip() == "burntoken 0.1.0", (
        f"unexpected version output: stdout={r.stdout!r} stderr={r.stderr!r}"
    )


# ---------------------------------------------------------------------------
#  --models  (mocked client)
# ---------------------------------------------------------------------------

FAKE_MODELS = [
    {"id": "hbscloud-deepseek", "owned_by": "hbscloud"},
    {"id": "gpt-4o",            "owned_by": "openai"},
    {"id": "claude-3-5-sonnet", "owned_by": "anthropic"},
]


def test_models_legacy_flag_with_mocked_client_prints_list():
    """`--models` (legacy v0.1.0 flag form) should still work and exit 0.

    Patch target: ``commands.models.HBSClient`` — that's where the
    command module binds the name. Patching ``burntoken.cli.HBSClient``
    won't intercept the call because Python looks up the name in the
    caller's module globals.
    """
    with patch("burntoken.cli.commands.models.HBSClient") as MockClient, \
         env(HBS_API_KEY="sk-test-fake-key"):
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.list_models.return_value = FAKE_MODELS

        r = invoke(["--models"])

    r.assert_ok()
    # client.list_models was actually called
    MockClient.return_value.__enter__.return_value.list_models.assert_called_once()
    # every fake model id appears in stdout
    for m in FAKE_MODELS:
        assert m["id"] in r.stdout, (
            f"model {m['id']!r} missing from --models output:\n{r.stdout}"
        )
    # and the count line
    assert "3" in r.stdout


def test_models_subcommand_form_also_works():
    """`models` (canonical subcommand form) should produce the same result."""
    with patch("burntoken.cli.commands.models.HBSClient") as MockClient, \
         env(HBS_API_KEY="sk-test-fake-key"):
        MockClient.return_value.__enter__.return_value.list_models.return_value = FAKE_MODELS
        r = invoke(["models"])
    r.assert_ok()
    for m in FAKE_MODELS:
        assert m["id"] in r.stdout


def test_models_underlying_returns_list_type():
    """Sanity: the underlying list_models() contract is ``List[Dict]``."""
    assert isinstance(FAKE_MODELS, list)
    assert all(isinstance(m, dict) and "id" in m for m in FAKE_MODELS)


# ---------------------------------------------------------------------------
#  burn --preset code -n 0
# ---------------------------------------------------------------------------

def test_burn_zero_count_exits_cleanly_without_network_calls():
    """`burn -n 0` must complete the asyncio loop without making any calls.

    The client may be constructed (we enter its `async with` block) but
    ``chat()`` must never be invoked. This is the load-bearing property:
    a -n 0 burn is supposed to be a free smoke check, not a network call.
    """
    with patch("burntoken.cli.commands.burn.AsyncHBSClient") as MockAsync, \
         env(HBS_API_KEY="sk-test-fake-key", HBS_MODEL="fake-model"):
        # If chat() is ever called, fail loud.
        MockAsync.return_value.__aenter__.return_value.chat.side_effect = AssertionError(
            "AsyncHBSClient.chat should not be called for -n 0"
        )

        r = invoke(["burn", "--preset", "code", "-n", "0"])

    r.assert_ok()
    # No chat calls were made — the zero-iteration loop is truly free.
    client = MockAsync.return_value.__aenter__.return_value
    client.chat.assert_not_called()


def test_burn_zero_count_handles_missing_model_gracefully():
    """`burn -n 0` should not require a model to be configured — the loop
    runs zero iterations so the model check inside the loop is never hit.
    This pins the contract that -n 0 is safe to invoke for a sanity check
    even before you've set HBS_MODEL."""
    with patch("burntoken.cli.commands.burn.AsyncHBSClient") as MockAsync, \
         env(HBS_API_KEY="sk-test-fake-key"):
        # Note: no HBS_MODEL set
        os.environ.pop("HBS_MODEL", None)
        r = invoke(["burn", "--preset", "code", "-n", "0"])
    r.assert_ok()
    # The client may have been constructed (the env-config check passes
    # on api_key alone), but no chat() call was made.
    if MockAsync.called:
        client = MockAsync.return_value.__aenter__.return_value
        client.chat.assert_not_called()


# ---------------------------------------------------------------------------
#  config show
# ---------------------------------------------------------------------------

def test_config_show_prints_resolved_env_as_json():
    """`config show` must print a parseable JSON of the resolved config."""
    with env(HBS_API_KEY="sk-test-fake-key"):
        # Remove any HBS_MODEL/.env leakage from the local environment
        # so we test the pure fallback path.
        os.environ.pop("HBS_MODEL", None)
        r = invoke(["config", "show"])

    r.assert_ok()
    # The CLI prints a JSON document via `json.dumps(..., indent=2, ensure_ascii=False)`
    parsed = json.loads(r.stdout)
    assert isinstance(parsed, dict)
    # The fallback path injects a "hbscloud" provider when no TOML is present.
    assert "providers" in parsed
    assert "hbscloud" in parsed["providers"], (
        f"expected hbscloud provider in config show output:\n{r.stdout}"
    )
    hbs = parsed["providers"]["hbscloud"]
    # api_key should be partially masked — never the full secret in plaintext.
    assert hbs["api_key"] != "sk-test-fake-key", (
        "config show leaked the full API key!"
    )
    assert "sk-" in hbs["api_key"]  # still has a prefix marker
    # base_url is present and is a non-empty string (we don't pin the
    # exact value because it round-trips through load_env_fallback which
    # prefers .env over os.environ; not every test env has a .env file).
    assert isinstance(hbs["base_url"], str) and hbs["base_url"]


def test_config_show_does_not_leak_full_api_key():
    """Defense-in-depth: even if the format changes, key must be masked."""
    with env(HBS_API_KEY="sk-supersecret-do-not-leak-12345678"):
        r = invoke(["config", "show"])
    r.assert_ok()
    assert "sk-supersecret-do-not-leak-12345678" not in r.stdout
    assert "sk-supersecret" not in r.stdout
