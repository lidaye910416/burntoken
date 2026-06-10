# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `HBS_VERIFY` environment variable now defaults to `false`, allowing the
  agent to run without mandatory verification prompts for faster iteration.
- `examples/` directory with runnable shell and REPL examples
  (`00-version.sh`, `01-single-call.sh`, `02-streaming.sh`,
  `03-batch-burn.sh`, `04-repl-session.txt`, `05-work-review.sh`,
  `06-models-list.txt`) for onboarding and manual smoke testing.
- `--log-file` CLI option for directing run output to a persistent log file
  in addition to stdout/stderr.
- `tests_py/` pytest suite covering CLI surface, CLI smoke, client,
  config, presets, and tracker modules (`test_cli_smoke.py`,
  `test_cli_surface.py`, `test_client.py`, `test_config.py`,
  `test_presets.py`, `test_tracker.py`) plus shared `conftest.py`
  and `helpers.py`.

### Changed
- `install.sh` promoted to the project root (was previously nested) so
  the canonical installer is discoverable at the top of the repository.
- CLI refactored into a dedicated `burntoken/` Python subpackage
  (with `cli/`, `cli.py`, `__main__.py`, `_version.py`) to clarify
  the import surface and enable `python -m burntoken` execution.

### Fixed
- (No fixes recorded yet in this entry.)
