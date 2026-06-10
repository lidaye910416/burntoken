"""Characterization tests for burntoken CLI surface.

These tests pin down the public CLI surface (commands, flags, defaults,
help/version strings) so the refactor of cli.py into a package cannot
silently change the user-visible contract.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "burntoken", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


# ----- top-level --help / --version ---------------------------------------

def test_top_level_help_succeeds():
    r = _run("--help")
    assert r.returncode == 0
    assert "burntoken" in r.stdout
    assert "{run,burn,repl,models,config,providers,use,team,review,work}" in r.stdout


def test_top_level_help_lists_all_subcommands():
    r = _run("--help")
    for sub in ("run", "burn", "repl", "models", "config", "providers",
                "use", "team", "review", "work"):
        assert sub in r.stdout, f"missing subcommand {sub!r} in --help"


def test_version_flag():
    r = _run("--version")
    assert r.returncode == 0
    assert r.stdout.strip() == "burntoken 0.1.0"


# ----- subcommand help ----------------------------------------------------

SUBCOMMAND_FLAGS = {
    "run": ["-h", "--help"],
    "burn": ["-n", "--count", "-P", "--parallel", "--preset", "--seed",
             "--save", "--max-tokens", "--max-cost", "--log-file"],
    "repl": ["-m", "--model", "-s", "--system", "-t", "--temperature",
             "--max-tokens", "--max-history", "--log-file"],
    "models": [],
    "config": [],
    "providers": [],
    "use": [],
    "team": ["--mode", "-n", "--count", "-P", "--parallel", "--max-tokens",
             "--max-cost", "--provider", "--model", "--no-reviewer",
             "--save", "--quiet"],
    "review": ["target", "--ref", "--refresh", "--no-cache", "--cache-dir",
               "--ext", "--recursive", "-m", "--model", "-n", "--count",
               "-P", "--parallel", "--max-tokens", "--max-cost",
               "--max-tokens-per-file", "--max-bytes", "--save", "--out-dir",
               "--show", "--show-chars", "--seed"],
    "work": ["path", "--git", "--git-ref", "--ext", "--recursive",
             "-m", "--model", "-n", "--count", "-P", "--parallel",
             "--max-tokens", "--max-cost", "--max-tokens-per-file",
             "--max-bytes", "--save", "--out-dir", "--show", "--show-chars",
             "--seed", "--log-file"],
}


@pytest.mark.parametrize("sub", list(SUBCOMMAND_FLAGS))
def test_subcommand_help_succeeds(sub):
    r = _run(sub, "--help")
    assert r.returncode == 0, f"{sub} --help failed: {r.stderr}"
    assert "options:" in r.stdout or "usage:" in r.stdout


@pytest.mark.parametrize("sub,flags", list(SUBCOMMAND_FLAGS.items()))
def test_subcommand_help_lists_flags(sub, flags):
    if not flags:
        pytest.skip(f"{sub} has no flags to check")
    r = _run(sub, "--help")
    for f in flags:
        assert f in r.stdout, f"{sub} --help missing {f!r}\nfull:\n{r.stdout}"


# ----- default command (bare `burntoken` defaults to `run`) ---------------

def test_bare_invocation_no_args_runs_default_command():
    # `burntoken` with no args is rewritten to `burntoken run` internally;
    # without a model+prompt it should exit non-zero but NOT raise.
    r = _run()
    # It will try to talk to HBS — expect either a config error (rc=1) or
    # a non-zero exit. The point is that argparse doesn't reject bare
    # invocation with a usage error.
    assert r.returncode != 2, f"bare run got usage-error:\n{r.stderr}"


# ----- legacy import surface ---------------------------------------------

def test_legacy_import_main_works():
    from burntoken.cli import main
    assert callable(main)


def test_legacy_import_path_does_not_break():
    # `import burntoken.cli` must still work (the shim re-exports main)
    import burntoken.cli as cli_mod
    assert hasattr(cli_mod, "main")


def test_legacy_import_path_has_main_attribute():
    # Even if cli.py is replaced by a shim, the `main` symbol must exist
    from burntoken.cli import main
    assert main.__name__ in ("main",)  # callable, name preserved


# ----- package surface ----------------------------------------------------

def test_package_exposes_subcommand_modules():
    # After refactor, commands/ subpackage should expose per-command files
    from burntoken.cli import commands
    for name in ("run", "burn", "repl", "models", "work", "team",
                 "providers", "use", "config", "review"):
        mod = getattr(commands, name, None)
        assert mod is not None, f"missing commands.{name}"


def test_parsers_module_exposes_build_parser():
    from burntoken.cli.parsers import build_parser
    parser = build_parser()
    assert parser.prog == "burntoken"


def test_banner_module_importable():
    from burntoken.cli import banner
    assert banner is not None


def test_repl_loop_module_importable():
    from burntoken.cli import repl_loop
    assert repl_loop is not None


# ----- 300-line file size invariant ---------------------------------------

CLI_DIR = REPO / "burntoken" / "cli"

@pytest.mark.parametrize("py_file", sorted(CLI_DIR.rglob("*.py")))
def test_no_cli_file_exceeds_300_lines(py_file):
    rel = py_file.relative_to(REPO)
    n = sum(1 for _ in py_file.open())
    assert n <= 300, f"{rel} has {n} lines (max 300)"
