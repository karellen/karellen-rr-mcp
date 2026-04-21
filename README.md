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
- **`perf_event_paranoid`** set to `1` to allow recording:
  ```bash
  sudo sysctl kernel.perf_event_paranoid=1
  ```

### Installing rr and GDB

**Via pip** (using [karellen-rr](https://github.com/karellen/karellen-rr)):
```bash
pip install karellen-rr-mcp[rr]
```

This installs rr as a pip package alongside karellen-rr-mcp. GDB must still be installed
separately via your system package manager.

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

rr requires access to hardware performance counters. Set `perf_event_paranoid` to `1`:

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

### Claude Code plugin (recommended)

The plugin automatically configures the MCP server and includes:

- **Crash detection hook** that suggests rr when a Bash command exits with a signal
  (SIGSEGV, SIGABRT, SIGBUS, etc.) or output contains crash/sanitizer signatures
- **`/karellen-rr-mcp:rr-debug` skill** that walks through the full
  record-replay-analyze workflow step by step
- **`rr-investigator` agent** that Claude can spawn to autonomously investigate
  crashes using rr reverse execution

From the [Karellen plugins marketplace](https://github.com/karellen/claude-plugins):

```bash
claude plugin marketplace add karellen/claude-plugins
claude plugin install karellen-rr-mcp@karellen-plugins
```

Or from the official Anthropic marketplace (if accepted):

```bash
claude plugin install karellen-rr-mcp@claude-plugins-official
```

Or load directly from a local checkout for testing:

```bash
claude --plugin-dir /path/to/karellen-rr-mcp
```

### Manual MCP server configuration

If you prefer not to use the plugin, you can configure the MCP server directly.
This gives you the MCP tools but not the skill, agent, or crash detection hook.

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

By default Claude Code will prompt for confirmation before each `rr_*` tool call.
You can approve individually by selecting "Yes, and don't ask again" when prompted.

To auto-approve all tools upfront, add a permission rule to your user settings
(`~/.claude/settings.json`):

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_karellen-rr-mcp_karellen-rr-mcp__*",
      "mcp__karellen-rr-mcp__*"
    ]
  }
}
```

The first rule covers plugin-loaded tools, the second covers manual MCP configuration.

Or for a project-scoped setting, add the same rule to `.claude/settings.json` in your
project root (this file can be committed to version control so all team members get it).

## Available Tools

### Session Lifecycle
| Tool | Description |
|------|-------------|
| `rr_record` | Record a command with rr. Returns trace directory path. |
| `rr_replay_start` | Start replay session (launches rr gdbserver + GDB/MI). |
| `rr_replay_stop` | Stop current replay session, clean up. |
| `rr_list_recordings` | List available rr trace recordings. |
| `rr_ps` | List processes in a trace recording (PID, PPID, exit code, command). |
| `rr_traceinfo` | Get trace metadata (header info in JSON format). |
| `rr_rm` | Remove an rr trace recording. |
| `rr_when` | Get current rr event number (position in trace). |

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

### Thread and Frame Navigation
| Tool | Description |
|------|-------------|
| `rr_thread_list` | List all threads with state and location. |
| `rr_thread_select` | Switch to a different thread. |
| `rr_select_frame` | Select a stack frame for inspection (locals/evaluate use that frame). |

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
