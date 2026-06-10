"""Tests for ``burntoken.config`` — HBS_* env loading + ProviderSpec defaults.

These are the red-phase tests for TDD. They exercise:

  1. ``load_hbs_env()`` returns a dict populated from the standard
     HBS_* environment variables, with ``HBS_VERIFY`` defaulting to
     ``False`` (hbscloud has cert-chain issues; the default is to skip).
  2. ``load_hbs_env()`` accepts falsy/truthy spellings for HBS_VERIFY
     (0/false/no/off → False ; 1/true/yes/on → True).
  3. ``load_hbs_env()`` returns sane defaults when no env is set
     (empty key, canonical base_url, empty model, verify=False).
  4. ``load_hbs_env()`` does not mutate ``os.environ`` (read-only helper).
  5. ``ProviderSpec.verify`` default is ``True`` at the dataclass level
     (the *spec* default; the *resolved env default* is False — see #3).
  6. ``Config.get_provider`` raises a clear error when no default is set.
"""
from __future__ import annotations

import os

import pytest

from burntoken.config import (
    Config,
    ProviderSpec,
    load_hbs_env,
)


# ---------------------------------------------------------------------------
#  load_hbs_env() — HBS_API_KEY
# ---------------------------------------------------------------------------

class TestLoadHbsEnvApiKey:
    def test_returns_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_API_KEY", "sk-test-abc")
        env = load_hbs_env()
        assert env["api_key"] == "sk-test-abc"

    def test_empty_string_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_API_KEY", raising=False)
        env = load_hbs_env()
        assert env["api_key"] == ""


# ---------------------------------------------------------------------------
#  load_hbs_env() — HBS_BASE_URL
# ---------------------------------------------------------------------------

class TestLoadHbsEnvBaseUrl:
    def test_returns_base_url_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_BASE_URL", "https://example.com/v1")
        env = load_hbs_env()
        assert env["base_url"] == "https://example.com/v1"

    def test_default_base_url_is_canonical_hbscloud(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_BASE_URL", raising=False)
        env = load_hbs_env()
        assert env["base_url"] == "https://model.hbscloud.com.cn/v1"


# ---------------------------------------------------------------------------
#  load_hbs_env() — HBS_MODEL
# ---------------------------------------------------------------------------

class TestLoadHbsEnvModel:
    def test_returns_model_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_MODEL", "hbscloud-deepseek-v3")
        env = load_hbs_env()
        assert env["model"] == "hbscloud-deepseek-v3"

    def test_empty_string_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_MODEL", raising=False)
        env = load_hbs_env()
        assert env["model"] == ""


# ---------------------------------------------------------------------------
#  load_hbs_env() — HBS_VERIFY (default = False)
# ---------------------------------------------------------------------------

class TestLoadHbsEnvVerify:
    """HBS_VERIFY must default to ``False`` because the hbscloud cert chain
    is broken in the deployment we target; users opt in by setting the var."""

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "off"])
    def test_falsy_spellings_disable_verify(self, monkeypatch, value):
        monkeypatch.setenv("HBS_VERIFY", value)
        env = load_hbs_env()
        assert env["verify"] is False, f"HBS_VERIFY={value!r} should be False"

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
    def test_truthy_spellings_enable_verify(self, monkeypatch, value):
        monkeypatch.setenv("HBS_VERIFY", value)
        env = load_hbs_env()
        assert env["verify"] is True, f"HBS_VERIFY={value!r} should be True"

    def test_default_is_false_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_VERIFY", raising=False)
        env = load_hbs_env()
        assert env["verify"] is False, "HBS_VERIFY must default to False (cert chain issue)"

    def test_whitespace_is_tolerated(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_VERIFY", "  true  ")
        env = load_hbs_env()
        assert env["verify"] is True


# ---------------------------------------------------------------------------
#  load_hbs_env() — purity / read-only contract
# ---------------------------------------------------------------------------

class TestLoadHbsEnvPurity:
    def test_does_not_mutate_os_environ(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_API_KEY", "sk-x")
        monkeypatch.setenv("HBS_BASE_URL", "https://x.test/v1")
        monkeypatch.setenv("HBS_MODEL", "m-x")
        monkeypatch.delenv("HBS_VERIFY", raising=False)
        before = dict(os.environ)
        load_hbs_env()
        after = dict(os.environ)
        assert before == after, "load_hbs_env() must not mutate os.environ"

    def test_returned_dict_has_expected_keys(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_API_KEY", raising=False)
        monkeypatch.delenv("HBS_BASE_URL", raising=False)
        monkeypatch.delenv("HBS_MODEL", raising=False)
        monkeypatch.delenv("HBS_VERIFY", raising=False)
        env = load_hbs_env()
        for k in ("api_key", "base_url", "model", "verify", "pricing"):
            assert k in env, f"load_hbs_env() must return key {k!r}"


# ---------------------------------------------------------------------------
#  ProviderSpec — dataclass defaults
# ---------------------------------------------------------------------------

class TestProviderSpecDefaults:
    def test_verify_default_is_true_at_dataclass_level(self):
        # The dataclass default is True; the env-resolution helper
        # overrides it to False by default. Both behaviours are tested.
        p = ProviderSpec(name="x")
        assert p.verify is True

    def test_timeout_default_is_180(self):
        p = ProviderSpec(name="x")
        assert p.timeout == 180.0

    def test_base_url_default_is_none(self):
        p = ProviderSpec(name="x")
        assert p.base_url is None


# ---------------------------------------------------------------------------
#  Config — get_provider error path
# ---------------------------------------------------------------------------

class TestConfigGetProvider:
    def test_missing_default_raises_value_error(self):
        cfg = Config()  # no default_provider, no providers
        with pytest.raises(ValueError, match="provider"):
            cfg.get_provider()

    def test_unknown_provider_raises_key_error(self):
        cfg = Config()
        cfg.providers["hbscloud"] = ProviderSpec(name="hbscloud", api_key="sk-x")
        cfg.default_provider = "hbscloud"
        with pytest.raises(KeyError, match="nope"):
            cfg.get_provider("nope")

    def test_get_provider_returns_default_when_no_name(self):
        cfg = Config()
        cfg.providers["hbscloud"] = ProviderSpec(name="hbscloud", api_key="sk-x")
        cfg.default_provider = "hbscloud"
        assert cfg.get_provider().name == "hbscloud"


# ---------------------------------------------------------------------------
#  Pricing + ProviderSpec parsed by _parse_pricing / _parse_provider
# ---------------------------------------------------------------------------

class TestParsePricing:
    def test_prompt_and_completion_keys(self):
        from burntoken.config import _parse_pricing
        p = _parse_pricing({"prompt_per_1k": 0.001, "completion_per_1k": 0.002})
        assert p.prompt_per_1k == 0.001
        assert p.completion_per_1k == 0.002

    def test_input_output_aliases(self):
        from burntoken.config import _parse_pricing
        p = _parse_pricing({"input_per_1k": 0.5, "output_per_1k": 1.5})
        assert p.prompt_per_1k == 0.5
        assert p.completion_per_1k == 1.5

    def test_missing_keys_default_to_zero(self):
        from burntoken.config import _parse_pricing
        p = _parse_pricing({})
        assert p.prompt_per_1k == 0.0
        assert p.completion_per_1k == 0.0


class TestParseProvider:
    def test_basic_provider(self):
        from burntoken.config import _parse_provider
        p = _parse_provider("hbs", {
            "type": "openai",
            "api_key": "sk-a",
            "base_url": "https://x.test/v1",
            "default_model": "m",
            "timeout": 60,
            "verify": False,
        })
        assert p.name == "hbs"
        assert p.type == "openai"
        assert p.api_key == "sk-a"
        assert p.base_url == "https://x.test/v1"
        assert p.default_model == "m"
        assert p.timeout == 60.0
        assert p.verify is False

    def test_provider_with_env_ref(self, monkeypatch):
        from burntoken.config import _parse_provider
        monkeypatch.setenv("MY_TEST_KEY", "sk-from-env")
        p = _parse_provider("h", {"api_key": "${MY_TEST_KEY}"})
        assert p.api_key == "sk-from-env"

    def test_provider_extra_keys_captured(self):
        from burntoken.config import _parse_provider
        p = _parse_provider("h", {
            "api_key": "k",
            "base_url": "u",
            "default_model": "m",
            "some_extra": "yes",
        })
        assert p.extra.get("some_extra") == "yes"

    def test_provider_default_type_is_openai(self):
        from burntoken.config import _parse_provider
        p = _parse_provider("h", {"api_key": "k"})
        assert p.type == "openai"


# ---------------------------------------------------------------------------
#  _resolve_env — string interpolation
# ---------------------------------------------------------------------------

class TestResolveEnv:
    def test_no_dollar_returns_input(self):
        from burntoken.config import _resolve_env
        assert _resolve_env("plain") == "plain"

    def test_dollar_brace(self, monkeypatch):
        from burntoken.config import _resolve_env
        monkeypatch.setenv("FOO", "bar")
        assert _resolve_env("${FOO}") == "bar"

    def test_dollar_bare(self, monkeypatch):
        from burntoken.config import _resolve_env
        monkeypatch.setenv("FOO", "bar")
        assert _resolve_env("$FOO") == "bar"

    def test_unset_var_keeps_literal(self, monkeypatch):
        from burntoken.config import _resolve_env
        monkeypatch.delenv("UNSET_VAR_X", raising=False)
        assert _resolve_env("${UNSET_VAR_X}") == "${UNSET_VAR_X}"

    def test_non_string_passthrough(self):
        from burntoken.config import _resolve_env
        assert _resolve_env(123) == 123


# ---------------------------------------------------------------------------
#  load_config / load_env_fallback / ensure_default_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_from_explicit_path(self, tmp_path):
        from burntoken.config import load_config
        toml = tmp_path / "c.toml"
        toml.write_text(
            'default_provider = "h"\n'
            '[providers.h]\n'
            'api_key = "sk-x"\n'
            'base_url = "https://x.test/v1"\n'
            'default_model = "m"\n'
            'timeout = 30\n'
            'verify = false\n'
        )
        cfg = load_config(str(toml))
        assert cfg.default_provider == "h"
        assert "h" in cfg.providers
        assert cfg.providers["h"].api_key == "sk-x"
        assert cfg.providers["h"].verify is False
        assert cfg.providers["h"].timeout == 30.0

    def test_load_with_team_block(self, tmp_path):
        from burntoken.config import load_config
        toml = tmp_path / "c.toml"
        toml.write_text(
            '[providers.h]\napi_key = "k"\n'
            '[team]\nmode = "pointless"\nparallel = 5\n'
            'strategist_provider = "h"\nstrategist_model = "m"\n'
        )
        cfg = load_config(str(toml))
        assert cfg.team.mode == "pointless"
        assert cfg.team.parallel == 5
        assert cfg.team.strategist_provider == "h"
        assert cfg.team.strategist_model == "m"

    def test_load_missing_file_returns_empty_config(self, tmp_path):
        from burntoken.config import load_config
        cfg = load_config(str(tmp_path / "nope.toml"))
        assert cfg.providers == {}
        assert cfg.default_provider is None

    def test_load_provider_with_pricing_aliases(self, tmp_path):
        from burntoken.config import load_config
        toml = tmp_path / "c.toml"
        toml.write_text(
            '[providers.h]\napi_key = "k"\n'
            'input_per_1k = 0.5\noutput_per_1k = 1.5\n'
        )
        cfg = load_config(str(toml))
        assert cfg.providers["h"].pricing.prompt_per_1k == 0.5
        assert cfg.providers["h"].pricing.completion_per_1k == 1.5


class TestLoadEnvFallback:
    def test_loads_from_cwd_env(self, tmp_path, monkeypatch):
        from burntoken.config import load_env_fallback
        env = tmp_path / ".env"
        env.write_text("FOO_BAR=hello\n# comment\nEMPTY=\nBURNTOKEN_CONFIG=\n")
        monkeypatch.chdir(tmp_path)
        # Make sure neither of the absolute candidates exist for this user
        monkeypatch.setattr(
            "os.path.expanduser",
            lambda p: p.replace("~/claude-code-hbscloud/.env", str(tmp_path / "missing"))
                    .replace("~/.claude-code-hbscloud/.env", str(tmp_path / "missing2")),
        )
        monkeypatch.setattr(
            "os.path.exists",
            lambda p: True if p == str(env) else False,
        )
        # load_env_fallback short-circuits on first candidate — easier path: just chdir.
        monkeypatch.undo()  # restore real expanduser/exists
        monkeypatch.chdir(tmp_path)
        out = load_env_fallback()
        assert out.get("FOO_BAR") == "hello"


class TestEnsureDefaultConfig:
    def test_creates_template_file(self, tmp_path, monkeypatch):
        from burntoken import config as cfg_mod
        target = tmp_path / "burntoken" / "config.toml"
        monkeypatch.setattr(cfg_mod, "default_config_path", lambda: target)
        result = cfg_mod.ensure_default_config()
        assert result == target
        assert target.exists()
        assert "default_provider" in target.read_text()


# ---------------------------------------------------------------------------
#  default_config_path — env → XDG → home
# ---------------------------------------------------------------------------

class TestDefaultConfigPath:
    def test_uses_burntoken_config_env_var(self, tmp_path, monkeypatch):
        from burntoken.config import default_config_path
        toml = tmp_path / "c.toml"
        toml.write_text("")
        monkeypatch.setenv("BURNTOKEN_CONFIG", str(toml))
        assert default_config_path() == toml

    def test_returns_none_when_nothing_exists(self, tmp_path, monkeypatch):
        from burntoken.config import default_config_path
        monkeypatch.setenv("BURNTOKEN_CONFIG", str(tmp_path / "nope.toml"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        # No files exist anywhere → None
        assert default_config_path() is None


# ---------------------------------------------------------------------------
#  set_active / get_active
# ---------------------------------------------------------------------------

class TestActiveProvider:
    def test_set_and_get_active(self, tmp_path, monkeypatch):
        from burntoken import config as cfg_mod
        active_file = tmp_path / "active"
        monkeypatch.setattr(cfg_mod, "_ACTIVE_FILE", active_file)
        cfg_mod.set_active("hbscloud")
        assert cfg_mod.get_active() == "hbscloud"

    def test_get_active_returns_none_when_unset(self, tmp_path, monkeypatch):
        from burntoken import config as cfg_mod
        active_file = tmp_path / "active"
        monkeypatch.setattr(cfg_mod, "_ACTIVE_FILE", active_file)
        assert cfg_mod.get_active() is None

    def test_get_active_empty_string_returns_none(self, tmp_path, monkeypatch):
        from burntoken import config as cfg_mod
        active_file = tmp_path / "active"
        active_file.write_text("   \n")
        monkeypatch.setattr(cfg_mod, "_ACTIVE_FILE", active_file)
        assert cfg_mod.get_active() is None


# ---------------------------------------------------------------------------
#  HBS_PRICE_PROMPT / HBS_PRICE_COMPLETION
# ---------------------------------------------------------------------------

class TestHbsEnvPricing:
    def test_pricing_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HBS_PRICE_PROMPT", "0.1")
        monkeypatch.setenv("HBS_PRICE_COMPLETION", "0.2")
        env = load_hbs_env()
        assert env["pricing"].prompt_per_1k == 0.1
        assert env["pricing"].completion_per_1k == 0.2

    def test_pricing_default_zero(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_PRICE_PROMPT", raising=False)
        monkeypatch.delenv("HBS_PRICE_COMPLETION", raising=False)
        env = load_hbs_env()
        assert env["pricing"].prompt_per_1k == 0.0
        assert env["pricing"].completion_per_1k == 0.0


# ---------------------------------------------------------------------------
#  Config.default() convenience
# ---------------------------------------------------------------------------

class TestConfigDefault:
    def test_default_returns_default_provider(self):
        cfg = Config()
        cfg.providers["h"] = ProviderSpec(name="h", api_key="k")
        cfg.default_provider = "h"
        assert cfg.default().name == "h"

    def test_env_path_is_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("HBS_API_KEY", raising=False)
        env = load_hbs_env()
        assert env["env_path"] is None
