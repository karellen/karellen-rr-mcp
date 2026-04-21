# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`karellen-rr-mcp` is an MCP server that enables LLM clients to use [rr](https://rr-project.org/) for reverse debugging. It records a failing program with rr, then replays it with full forward and reverse debugging via GDB/MI (using pygdbmi), so the LLM can inspect program state without modifying source code.

## Build & Test

This is a PyBuilder project. The build tool is `pyb`.

```bash
pyb                          # default: analyze + publish (lint, test, coverage, package)
pyb run_unit_tests           # run all unit tests only
pyb analyze                  # lint (flake8) + test + coverage
```

Run a single test module by overriding the `unittest_module_glob` property:

```bash
pyb run_unit_tests -P unittest_module_glob=mi_commands_tests
```

Tests live in `src/unittest/python/*_tests.py` and use `unittest` with `unittest.mock`.

## Lint

Flake8 with: `max_line_length=130`, `extend_ignore=E303,E402`. Applies to source, tests, and scripts. Flake8 violations break the build.

## Architecture

Two-process model per debugging session:

1. **rr gdbserver** (`rr replay -s <port>`) -- managed by `rr_manager.ReplayServer`
2. **GDB/MI** via pygdbmi `GdbController` -- managed by `gdb_session.GdbSession`

Module responsibilities:

- **`server.py`** -- FastMCP server definition, all `@mcp.tool()` endpoints, module-level singleton session state (`_replay_server`, `_gdb_session`), cleanup/signal handling, and `main()` entry point. The `_tag_errors` decorator converts all exceptions to `ToolError` with prefixed messages (`gdb:`, `rr:`, `internal:`).
- **`rr_manager.py`** -- Subprocess lifecycle: `record()` runs `rr record`, `ReplayServer` starts/stops `rr replay` gdbserver, helper functions for `rr ps`, `rr traceinfo`, `rr rm`, listing traces. Port allocation via ephemeral socket binding.
- **`gdb_session.py`** -- Wraps pygdbmi `GdbController`. `_write_until()` is the core I/O loop: sends a GDB/MI command and keeps reading responses until a predicate is satisfied or deadline expires. All timeouts are configurable via `RR_MCP_TIMEOUT_*` environment variables.
- **`mi_commands.py`** -- Pure functions returning GDB/MI command strings. Reverse execution uses CLI commands (`rc`, `reverse-step`, etc.) because MI has no reverse equivalents. `rr_when`, `rr_seek`, `checkpoint_save/restore` use `-interpreter-exec console`.
- **`response_parser.py`** -- Pure functions parsing pygdbmi response dicts into domain dataclasses. Key helpers: `find_result_response()`, `find_stop_event()`, `get_console_output()`, `is_error()`.
- **`types.py`** -- Dataclasses for all MCP tool return types (`Breakpoint`, `Frame`, `StopEvent`, `Variable`, `ThreadInfo`, etc.).

## Claude Code Plugin Artifacts

The repository doubles as a Claude Code plugin (loaded via `--plugin-dir` or marketplace):

- **`.claude-plugin/plugin.json`** -- Plugin manifest (name, version, description)
- **`hooks/hooks.json`** -- SessionStart prerequisite check + PostToolUse/PostToolUseFailure crash detection
- **`scripts/check-prerequisites.sh`** -- Checks for `karellen-rr-mcp`, `rr`, `gdb` on PATH
- **`scripts/detect-crash.sh`** -- Detects crash signals (exit codes 129-159, text patterns like SIGSEGV/SIGABRT/sanitizer output) and suggests rr debugging
- **`agents/rr-investigator.md`** -- Agent definition for autonomous crash investigation
- **`skills/rr-debug*/SKILL.md`** -- Four skill variants: general crash, logic bug, failing test, data race

When changing tool semantics, MCP server behavior, or environment variable handling, update the relevant plugin artifacts (skills, agent, hooks, scripts) in the same commit.

## CI

GitHub Actions (`.github/workflows/build.yml`): matrix build on ubuntu-latest across Python 3.10-3.14. Deploy (PyPI upload) from Python 3.14 on push to master. Uses `pybuilder/build@master` action. Commit messages containing `[release]` or `[release <version>]` trigger a release.
