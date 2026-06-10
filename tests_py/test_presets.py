"""Tests for burntoken.presets — prompt shape, max_tokens, temperature per preset.

These tests pin the public contract of the 5 built-in presets:
- chat   : temp 1.0, max_tokens 128
- math   : temp 0.3, max_tokens 512
- code   : temp 0.4, max_tokens 768
- essay  : temp 0.9, max_tokens 2048
- longctx: temp 0.5, max_tokens 512

Plus structural guarantees (system prompt non-empty, user templates list,
sample() shape, longctx_filler shape, make_plan wiring).
"""
from __future__ import annotations

import random

import pytest

from burntoken.presets import (
    BurnPlan,
    Preset,
    get,
    list_names,
    longctx_filler,
    make_plan,
)


# ---------- canonical (name, temperature, max_tokens) table ----------

EXPECTED = {
    "chat":    {"temperature": 1.0, "max_tokens": 128},
    "math":    {"temperature": 0.3, "max_tokens": 512},
    "code":    {"temperature": 0.4, "max_tokens": 768},
    "essay":   {"temperature": 0.9, "max_tokens": 2048},
    "longctx": {"temperature": 0.5, "max_tokens": 512},
}


# ---------- list / get ----------

def test_list_names_returns_all_five_presets():
    names = list_names()
    assert isinstance(names, list)
    assert set(names) == {"chat", "math", "code", "essay", "longctx"}
    assert len(names) == 5


def test_get_returns_preset_instance_for_each_name():
    for name in EXPECTED:
        p = get(name)
        assert isinstance(p, Preset)
        assert p.name == name


def test_get_raises_keyerror_for_unknown_preset():
    with pytest.raises(KeyError) as excinfo:
        get("does-not-exist")
    # The error message should mention the unknown name and the valid options.
    msg = str(excinfo.value)
    assert "does-not-exist" in msg
    for n in EXPECTED:
        assert n in msg


# ---------- per-preset param pinning ----------

@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_has_expected_temperature(preset_name):
    p = get(preset_name)
    assert p.temperature == EXPECTED[preset_name]["temperature"], (
        f"{preset_name} temperature drifted: {p.temperature}"
    )


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_has_expected_max_tokens(preset_name):
    p = get(preset_name)
    assert p.max_tokens == EXPECTED[preset_name]["max_tokens"], (
        f"{preset_name} max_tokens drifted: {p.max_tokens}"
    )


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_temperature_is_in_valid_range(preset_name):
    # LLM temperature is conventionally in [0.0, 2.0]. Pinning a sanity range
    # protects against accidental 100.0 / NaN regressions.
    p = get(preset_name)
    assert 0.0 <= p.temperature <= 2.0
    assert isinstance(p.temperature, float)


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_max_tokens_is_positive_int(preset_name):
    p = get(preset_name)
    assert isinstance(p.max_tokens, int)
    assert p.max_tokens > 0
    # And not absurdly huge — keep within a reasonable upper bound.
    assert p.max_tokens <= 8192


# ---------- prompt shape ----------

@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_has_non_empty_system_prompt(preset_name):
    p = get(preset_name)
    assert isinstance(p.system, str)
    assert p.system.strip(), f"{preset_name} has empty system prompt"


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_has_user_templates(preset_name):
    p = get(preset_name)
    assert isinstance(p.user_templates, list)
    assert len(p.user_templates) >= 1, (
        f"{preset_name} should have at least one user template"
    )
    for tpl in p.user_templates:
        assert isinstance(tpl, str)
        assert tpl.strip(), f"{preset_name} has an empty user template"


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_each_preset_has_description(preset_name):
    p = get(preset_name)
    assert isinstance(p.description, str)
    assert p.description.strip()


# ---------- sample() return shape ----------

@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_sample_returns_expected_tuple_shape(preset_name):
    p = get(preset_name)
    rng = random.Random(42)
    out = p.sample(rng)
    assert isinstance(out, tuple)
    assert len(out) == 3

    prompt, max_tokens, temperature = out
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert isinstance(max_tokens, int)
    assert max_tokens == p.max_tokens
    assert isinstance(temperature, float)
    assert temperature == p.temperature


@pytest.mark.parametrize("preset_name", list(EXPECTED))
def test_sample_replaces_seed_placeholder(preset_name):
    p = get(preset_name)
    rng = random.Random(123)
    prompt, _, _ = p.sample(rng)
    # No leftover literal {seed} token should remain in the rendered prompt.
    assert "{seed}" not in prompt
    # And the rendered prompt should be one of the registered templates.
    # (Strip the {seed} substitution and compare to a sanitized template.)
    normalized_templates = {tpl.replace("{seed}", "") for tpl in p.user_templates}
    # The rendered prompt must start with one of the template prefixes.
    assert any(prompt.startswith(t) for t in normalized_templates), (
        f"{preset_name}.sample() produced prompt that does not match any template: {prompt!r}"
    )


def test_sample_is_deterministic_with_same_seed():
    p = get("math")
    a = p.sample(random.Random(7))
    b = p.sample(random.Random(7))
    assert a == b


def test_sample_varies_across_seeds():
    p = get("chat")
    seen = {p.sample(random.Random(i))[0] for i in range(50)}
    # With 8 templates and 50 draws we should hit more than one prompt.
    assert len(seen) > 1


# ---------- longctx_filler ----------

def test_longctx_filler_returns_paired_rounds():
    rounds = 6
    pairs = longctx_filler(seed=1, rounds=rounds)
    assert isinstance(pairs, list)
    assert len(pairs) == rounds * 2  # user + assistant per round
    for i in range(0, len(pairs), 2):
        role_u, text_u = pairs[i]
        role_a, text_a = pairs[i + 1]
        assert role_u == "user"
        assert role_a == "assistant"
        assert isinstance(text_u, str) and text_u
        assert isinstance(text_a, str) and text_a


def test_longctx_filler_is_deterministic_per_seed():
    a = longctx_filler(seed=42, rounds=4)
    b = longctx_filler(seed=42, rounds=4)
    assert a == b


def test_longctx_filler_changes_with_seed():
    # Two different seeds should produce different filler text (probabilistically
    # overwhelming — if they collide, raise the rounds).
    a = longctx_filler(seed=1, rounds=10)
    b = longctx_filler(seed=999, rounds=10)
    assert a != b


# ---------- make_plan / BurnPlan wiring ----------

def test_make_plan_resolves_preset_and_counts():
    plan = make_plan("code", count=20, parallel=4)
    assert isinstance(plan, BurnPlan)
    assert plan.preset.name == "code"
    assert plan.preset.temperature == 0.4
    assert plan.preset.max_tokens == 768
    assert plan.n_requests == 20
    assert plan.parallel == 4
    assert plan.multi_turn == 1  # default


def test_make_plan_propagates_multi_turn():
    plan = make_plan("longctx", count=5, parallel=2, multi_turn=8)
    assert plan.preset.name == "longctx"
    assert plan.multi_turn == 8


def test_make_plan_unknown_preset_raises():
    with pytest.raises(KeyError):
        make_plan("nope", count=1, parallel=1)
