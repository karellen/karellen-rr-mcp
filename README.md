# MCP Server for rr Reverse Debugging (karellen-rr-mcp)

[![Gitter](https://img.shields.io/gitter/room/karellen/lobby?logo=gitter)](https://gitter.im/karellen/Lobby)
[![Build Status](https://img.shields.io/github/actions/workflow/status/karellen/karellen-rr-mcp/build.yml?branch=master)](https://github.com/karellen/karellen-rr-mcp/actions/workflows/build.yml)
[![Coverage Status](https://img.shields.io/coveralls/github/karellen/karellen-rr-mcp/master?logo=coveralls)](https://coveralls.io/r/karellen/karellen-rr-mcp?branch=master)

[![karellen-rr-mcp Version](https://img.shields.io/pypi/v/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Python Versions](https://img.shields.io/pypi/pyversions/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Day](https://img.shields.io/pypi/dd/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Week](https://img.shields.io/pypi/dw/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)
[![karellen-rr-mcp Downloads Per Month](https://img.shields.io/pypi/dm/karellen-rr-mcp?logo=pypi)](https://pypi.org/project/karellen-rr-mcp/)

## Overview

`karellen-rr-mcp` is an [MCP](https://modelcontextprotocol.io/) (Model Context Protocol)
server that enables any MCP-compliant LLM client to use [rr](https://rr-project.org/) for
reverse debugging. Instead of iteratively adding debug output and rebuilding, the LLM can
record a failing test with rr, then replay it with full forward and reverse debugging via
GDB/MI, inspecting program state without modifying source code.

## Requirements

- **Linux** on x86-64 (rr only supports Linux; aarch64 is experimental)
- **[rr](https://rr-project.org/)** installed and on PATH
- **[GDB](https://www.sourceware.org/gdb/)** installed and on PATH (used by rr for debugging)
- **Python** >= 3.10
- **`perf_event_paranoid`** set to allow recording (`<= 1`):
  ```bash
  sudo sysctl kernel.perf_event_paranoid=1
  ```

### Installing rr and GDB

**Fedora / RHEL / CentOS:**
```bash
sudo dnf install rr gdb
```

**Ubuntu / Debian:**
```bash
sudo apt install rr gdb
```

**Arch Linux:**
```bash
sudo pacman -S rr gdb
```

### Configuring perf_event_paranoid

rr requires access to hardware performance counters. Set `perf_event_paranoid` to `1`
or lower:

```bash
sudo sysctl kernel.perf_event_paranoid=1
```

To make this persistent across reboots:

```bash
echo 'kernel.perf_event_paranoid=1' | sudo tee /etc/sysctl.d/50-rr.conf
```

### Verify the setup

```bash
rr record /bin/true && echo "rr is working"
```

If this fails with a permissions error, check `perf_event_paranoid`. If it fails inside
a container or VM, note that rr requires access to CPU performance counters — it does
not work in most containers (Docker, Podman) or VMs unless hardware PMU passthrough is
configured.

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

### Auto-approve rr tools

By default Claude Code will prompt for confirmation before each `rr_*` tool call. To
auto-approve all tools from this server, add a permission rule to your user settings
(`~/.claude/settings.json`):

```json
{
  "permissions": {
    "allow": [
      "mcp__karellen-rr-mcp__*"
    ]
  }
}
```

Or for a project-scoped setting, add the same rule to `.claude/settings.json` in your
project root (this file can be committed to version control so all team members get it).

### Teach Claude the debugging workflow

Claude will automatically discover all `rr_*` tools, but to teach it **when and how** to
use them effectively, add the following to your project's `CLAUDE.md`:

````markdown
## Reverse Debugging with rr

### When to Use rr

Run tests and code normally. When you encounter a crash, segfault, test failure, or bug,
first check the relevant source code — if the fix is apparent without deep or broad
searches, just fix it directly. But if the cause isn't obvious after an initial look,
**switch to rr** rather than continuing to read through layers of code:

```
rr_record(command=["make", "test"])
rr_record(command=["./failing_test"])
rr_record(command=["ctest", "--test-dir", "build"], working_directory="/path/to/project")
rr_record(command=["./my_test"], trace_dir="/tmp/my-trace")
```

Keep the record-replay-debug cycle going until all problems are resolved. rr captures
the full execution deterministically, so the failure is replayed exactly as it happened.

rr is not just for crashes and race conditions — use it for any bug where you would
otherwise need to trace execution through multiple functions or files. Stepping through
actual execution in the debugger is faster and more reliable than extensive static
analysis.

### Debugging Multi-Process Recordings

When rr records a process that spawns children (e.g. a test harness that launches a
server), all subprocesses are captured in the trace. By default, `rr_replay_start()`
replays the root process. To debug a specific subprocess:

1. **List processes**: `rr_ps(trace_dir="/path/to/trace")` — shows PID, PPID, exit code,
   and command for every process in the recording
2. **Start replay of a specific process**:
   `rr_replay_start(trace_dir="/path/to/trace", pid=<pid>)` — replays only that
   subprocess
3. Debug as usual with breakpoints, reverse execution, etc.

This is essential for debugging crashes in child processes (e.g. a database server
launched by a test runner).

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

- **Re-run under rr when the fix isn't obvious**: if a quick look at the source doesn't
  reveal the cause, re-run with `rr_record` and debug the trace — don't waste cycles
  on deep static analysis or adding printf statements
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
  so multi-process and multi-threaded bugs can be debugged deterministically. Use
  `rr_ps(trace_dir)` to list all processes in a recording and
  `rr_replay_start(trace_dir, pid=<pid>)` to replay a specific subprocess
- **Traces are deterministic**: replaying a trace always reproduces the exact same
  execution, including thread interleavings and signal delivery — race conditions and
  heisenbugs that are impossible to reproduce with printf become trivially repeatable
- **Traces survive the session**: rr traces are stored in `~/.local/share/rr/` by default
  and persist across sessions. Use `rr_list_recordings()` to see available traces and
  `rr_replay_start(trace_dir="/path/to/trace")` to replay an older one
- **Custom trace directories**: use `rr_record(command, trace_dir="/path/to/dir")` to
  save recordings to a specific directory instead of the default `~/.local/share/rr/`
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
| `rr_ps` | List processes in a trace recording (PID, PPID, exit code, command). |

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

## Configuration

### Timeouts

All timeouts are configurable via environment variables (in seconds). Set them in your
MCP server configuration:

```json
{
  "mcpServers": {
    "karellen-rr-mcp": {
      "type": "stdio",
      "command": "karellen-rr-mcp",
      "env": {
        "RR_MCP_TIMEOUT_FORWARD": "300",
        "RR_MCP_TIMEOUT_REVERSE": "600"
      }
    }
  }
}
```

| Variable | Default | Description |
|----------|---------|-------------|
| `RR_MCP_TIMEOUT_STARTUP` | 30 | Waiting for rr gdbserver to start listening |
| `RR_MCP_TIMEOUT_CONNECT` | 60 | GDB connecting to rr (includes symbol loading) |
| `RR_MCP_TIMEOUT_FORWARD` | 120 | Forward execution (continue, step, next, finish) |
| `RR_MCP_TIMEOUT_REVERSE` | 300 | Reverse execution |
| `RR_MCP_TIMEOUT_BREAKPOINT` | 30 | Breakpoint/watchpoint operations |
| `RR_MCP_TIMEOUT_EVAL` | 30 | State inspection (backtrace, evaluate, locals, etc.) |

For large binaries (e.g. MariaDB, Firefox), you may need to increase `RR_MCP_TIMEOUT_CONNECT`
(symbol loading can take 20+ seconds) and `RR_MCP_TIMEOUT_FORWARD` (replaying to a
breakpoint deep in execution can take minutes).

## Troubleshooting

### AMD Zen CPUs

rr does not work reliably on AMD Zen CPUs unless the hardware SpecLockMap optimization
is disabled. When running rr on Zen you may see:

> On Zen CPUs, rr will not work reliably unless you disable the hardware SpecLockMap
> optimization.

**Workaround:** run the `zen_workaround.py` script from the
[rr source tree](https://github.com/rr-debugger/rr) as root:

```bash
sudo python3 scripts/zen_workaround.py
```

This fix must be reapplied after each reboot or suspend. To make it persist, you must
also stabilize the Speculative Store Bypass (SSB) mitigation by adding one of the
following kernel command-line parameters:

- `spec_store_bypass_disable=on` — fully enables SSB mitigation (has performance
  implications)
- `nospec_store_bypass_disable` — fully disables SSB mitigation (has security
  implications)

Alternatively, build and load the `zen_workaround.ko` kernel module from the rr source
tree, which prevents SSB mitigation from resetting the workaround without requiring
kernel parameters.

See the [rr Zen wiki page](https://github.com/rr-debugger/rr/wiki/Zen) for full details.

### MSR kernel module not loaded

The `zen_workaround.py` script accesses CPU model-specific registers via `/dev/cpu/0/msr`,
which requires the `msr` kernel module. On many distributions this module is not loaded
by default. If the script fails, load it manually:

```bash
sudo modprobe msr
```

To make this persistent across reboots:

```bash
echo 'msr' | sudo tee /etc/modules-load.d/msr.conf
```

**Note:** on systems with Secure Boot enabled, the `msr` module may fail to load because
it is not signed. You may need to either disable Secure Boot in your UEFI/BIOS settings,
or sign the module with your own Machine Owner Key (MOK).

### MADV_GUARD_INSTALL crash on kernel 6.13+ with glibc 2.42+

Linux 6.13 introduced `MADV_GUARD_INSTALL` (madvise advice 102) for lightweight stack
guard pages. glibc 2.42+ (e.g. Fedora 43) uses this in `pthread_create`. rr 5.9.0
(the latest release, from February 2025) does not recognize this madvise advice value
and crashes with:

```
Assertion `t->regs().syscall_result_signed() == -syscall_state.expect_errno' failed to hold.
Expected EINVAL for 'madvise' but got result 0 (errno SUCCESS); unknown madvise(102)
```

This was fixed in rr git master
([commit 34ff3a7](https://github.com/rr-debugger/rr/commit/34ff3a700), August 2025)
but has not been included in a release yet. **You must build rr from source** to get
the fix:

```bash
git clone https://github.com/rr-debugger/rr.git
cd rr
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

See [rr-debugger/rr#4044](https://github.com/rr-debugger/rr/issues/4044) and
[rr-debugger/rr#3995](https://github.com/rr-debugger/rr/issues/3995) for details.

## License

Apache-2.0
