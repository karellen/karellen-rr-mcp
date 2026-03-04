# karellen-rr-mcp

[![Gitter](https://img.shields.io/gitter/room/karellen/lobby?logo=gitter)](https://gitter.im/karellen/Lobby)
[![Build Status](https://img.shields.io/github/actions/workflow/status/karellen/karellen-rr-mcp/build.yml?branch=master)](https://github.com/karellen/karellen-rr-mcp/actions/workflows/build.yml)
[![Coverage Status](https://img.shields.io/coveralls/github/karellen/karellen-rr-mcp/master?logo=coveralls)](https://coveralls.io/r/karellen/karellen-rr-mcp?branch=master)

[![karellen-rr-mcp Version](https://img.shields.io/pypi/v/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Python Versions](https://img.shields.io/pypi/pyversions/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Day](https://img.shields.io/pypi/dd/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Week](https://img.shields.io/pypi/dw/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Month](https://img.shields.io/pypi/dm/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)

MCP Server for rr Reverse Debugging.

## Overview

`karellen-rr-mcp` is an [MCP](https://modelcontextprotocol.io/) (Model Context Protocol)
server that enables any MCP-compliant LLM client to use [rr](https://rr-project.org/) for
reverse debugging. Instead of iteratively adding debug output and rebuilding, the LLM can
record a failing test with rr, then replay it with full forward and reverse debugging via
GDB/MI, inspecting program state without modifying source code.

## Requirements

- Linux (rr only supports Linux)
- [rr](https://rr-project.org/) installed and on PATH
- Python >= 3.9
- `perf_event_paranoid` set to allow recording (`<= 1`):
  ```bash
  sudo sysctl kernel.perf_event_paranoid=1
  ```

## Installation

```bash
pip install karellen-rr-mcp
```

Or with pipx for an isolated environment:

```bash
pipx install karellen-rr-mcp
```

## Claude Code Integration

### Configure the MCP server

Using the CLI:

```bash
claude mcp add --transport stdio karellen-rr-mcp -- karellen-rr-mcp
```

Or manually add to `~/.claude.json` (user scope) or `.mcp.json` in your project root
(project scope, shared via version control):

```json
{
  "mcpServers": {
    "karellen-rr-mcp": {
      "type": "stdio",
      "command": "karellen-rr-mcp"
    }
  }
}
```

If installed with pipx:

```bash
claude mcp add --transport stdio karellen-rr-mcp -- pipx run karellen-rr-mcp
```

or manually:

```json
{
  "mcpServers": {
    "karellen-rr-mcp": {
      "type": "stdio",
      "command": "pipx",
      "args": ["run", "karellen-rr-mcp"]
    }
  }
}
```

### Teach Claude the debugging workflow

Claude will automatically discover all `rr_*` tools, but to teach it **when and how** to
use them effectively, add the following to your project's `CLAUDE.md`:

````markdown
## Reverse Debugging with rr

### When to Use rr

Run tests and code normally. When you encounter a crash, segfault, test failure, or bug
that is hard to understand from the output alone, **re-run the failing command under rr
recording** and then debug it:

```
rr_record(command=["make", "test"])
rr_record(command=["./failing_test"])
rr_record(command=["ctest", "--test-dir", "build"], working_directory="/path/to/project")
```

Keep the record-replay-debug cycle going until all problems are resolved. rr captures
the full execution deterministically, so the failure is replayed exactly as it happened.

### Debugging a SIGSEGV or Crash

When a crash occurs, re-run the crashing command with `rr_record`, then debug backwards:

1. **Start replay**: `rr_replay_start()`
2. **Run forward to the crash**: `rr_continue()` — the program will stop at the signal
   (SIGSEGV, SIGABRT, etc.) with the crashing frame
3. **Examine the crash site**: `rr_backtrace()` to see the full call stack,
   `rr_locals()` to see variable values, `rr_evaluate("*ptr")` to inspect the
   faulting pointer or expression
4. **Reverse-step to find the root cause**: `rr_next(reverse=True)` or
   `rr_step(reverse=True)` to walk backwards from the crash instruction-by-instruction,
   watching how variables and memory changed
5. **Set a watchpoint and reverse-continue**: if a variable or pointer was corrupted,
   use `rr_watchpoint_set("my_var")` then `rr_continue(reverse=True)` — this will stop
   at the exact moment the variable was last modified before the crash
6. **Use checkpoints**: `rr_checkpoint_save()` at interesting points so you can
   `rr_checkpoint_restore(id)` to jump back without replaying from the start
7. **Clean up**: `rr_replay_stop()` when the bug is understood

### General Debugging Workflow

For non-crash bugs (wrong output, logic errors, test assertion failures):

1. **Record** the failing test: `rr_record(command=["./failing_test"])`
2. **Start replay**: `rr_replay_start()`
3. **Set breakpoints** at the assertion or where wrong behavior is observed:
   `rr_breakpoint_set("test_function")` or `rr_breakpoint_set("file.c:42")`
4. **Run forward** to the breakpoint: `rr_continue()`
5. **Inspect state**: `rr_backtrace()`, `rr_locals()`, `rr_evaluate("expr")`
6. **Go backward** to find where state diverged: `rr_continue(reverse=True)`,
   `rr_step(reverse=True)`, `rr_next(reverse=True)`
7. **Clean up**: `rr_replay_stop()`

### Key Principles

- **Re-run under rr when stuck**: if a test fails or a program crashes and the cause
  isn't obvious from the output, re-run with `rr_record` and debug the trace — don't
  waste cycles adding printf statements
- **Work backwards from symptoms**: go forward to where the bug manifests, then reverse
  to find the cause — this is the opposite of printf-debugging and far more efficient
- **Watchpoints + reverse = root cause**: setting a watchpoint on a corrupted variable
  and reverse-continuing finds the exact write that caused corruption
- **Never modify source to debug**: rr replay gives full access to program state at every
  point in execution — no need for debug prints, trace output, or conditional breakpoints
  in source code

### rr Best Practices

- **Build with debug symbols**: compile with `-g` (and preferably `-O0` or `-Og`) so that
  rr traces include full source-level information — function names, line numbers, local
  variables, and type info are all available during replay
- **rr records the entire process tree**: child processes and threads are all captured,
  so multi-process and multi-threaded bugs can be debugged deterministically
- **Traces are deterministic**: replaying a trace always reproduces the exact same
  execution, including thread interleavings and signal delivery — race conditions and
  heisenbugs that are impossible to reproduce with printf become trivially repeatable
- **Traces survive the session**: rr traces are stored in `~/.local/share/rr/` by default
  and persist across sessions. Use `rr_list_recordings()` to see available traces and
  `rr_replay_start(trace_dir="/path/to/trace")` to replay an older one
- **Multiple replays from one recording**: a single trace can be replayed as many times
  as needed with different breakpoints and inspection strategies — no need to re-record
- **Conditional breakpoints narrow the search**: use
  `rr_breakpoint_set("file.c:100", condition="i == 42")` to stop only when specific
  conditions hold, then reverse from there
- **Checkpoints avoid re-replaying**: save checkpoints at key points with
  `rr_checkpoint_save()` and jump back to them with `rr_checkpoint_restore(id)` instead
  of replaying from the beginning
- **rr has overhead constraints**: rr only supports Linux on x86-64 (and experimentally
  aarch64), does not support programs that use hardware performance counters directly,
  and adds ~1.2x slowdown for CPU-bound code (more for I/O-heavy or syscall-heavy code)
- **Environment variables in recording**: pass `env={"MALLOC_CHECK_": "3"}` or similar
  to `rr_record` to enable additional runtime checks during recording that may surface
  bugs earlier
````

## Available Tools

### Session Lifecycle
| Tool | Description |
|------|-------------|
| `rr_record` | Record a command with rr. Returns trace directory path. |
| `rr_replay_start` | Start replay session (launches rr gdbserver + GDB/MI). |
| `rr_replay_stop` | Stop current replay session, clean up. |
| `rr_list_recordings` | List available rr trace recordings. |

### Breakpoints
| Tool | Description |
|------|-------------|
| `rr_breakpoint_set` | Set breakpoint at function/file:line/address. |
| `rr_breakpoint_remove` | Remove a breakpoint. |
| `rr_breakpoint_list` | List all breakpoints. |
| `rr_watchpoint_set` | Set hardware watchpoint (write/read/access). |

### Execution Control
| Tool | Description |
|------|-------------|
| `rr_continue` | Continue forward or backward. |
| `rr_step` | Step into (forward or reverse). |
| `rr_next` | Step over (forward or reverse). |
| `rr_finish` | Run to function return (or call site if reverse). |
| `rr_run_to_event` | Jump to specific rr event number. |

### State Inspection
| Tool | Description |
|------|-------------|
| `rr_backtrace` | Get call stack. |
| `rr_evaluate` | Evaluate C/C++ expression in current context. |
| `rr_locals` | List local variables with values. |
| `rr_read_memory` | Read raw memory bytes. |
| `rr_registers` | Read CPU registers. |
| `rr_source_lines` | List source code around current position. |

### Checkpoints
| Tool | Description |
|------|-------------|
| `rr_checkpoint_save` | Save checkpoint at current position. |
| `rr_checkpoint_restore` | Restore to saved checkpoint. |

## License

Apache-2.0
