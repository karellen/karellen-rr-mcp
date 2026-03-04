#   -*- coding: utf-8 -*-
#   Copyright 2026 Karellen, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""FastMCP server with tool definitions for rr reverse debugging."""

import atexit
import logging
import signal

from mcp.server.fastmcp import FastMCP

from karellen_rr_mcp.gdb_session import GdbSession, GdbSessionError
from karellen_rr_mcp.rr_manager import (
    record as rr_record_cmd,
    list_recordings as rr_list,
    list_processes as rr_ps_cmd,
    ReplayServer, RrError,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("karellen-rr-mcp", instructions=(
    "rr reverse debugging server. Use rr_record to record a failing test, "
    "rr_replay_start to begin debugging, then use execution control and "
    "inspection tools to investigate. Use reverse=True to go backwards."
))

# Module-level singleton session state
_replay_server = None
_gdb_session = None


def _cleanup():
    global _replay_server, _gdb_session
    if _gdb_session is not None:
        try:
            _gdb_session.close()
        except Exception:
            pass
        _gdb_session = None
    if _replay_server is not None:
        try:
            _replay_server.stop()
        except Exception:
            pass
        _replay_server = None


atexit.register(_cleanup)


def _handle_signal(signum, frame):
    _cleanup()


signal.signal(signal.SIGTERM, _handle_signal)


def _require_session():
    if _gdb_session is None or not _gdb_session.is_connected():
        raise GdbSessionError("No active replay session. Call rr_replay_start first.")
    return _gdb_session


def _format_stop_event(stop):
    if stop is None:
        return "Program stopped (no details available)"
    parts = ["Stopped: %s" % stop.reason]
    if stop.frame:
        f = stop.frame
        loc = f.function or "??"
        if f.file and f.line:
            loc += " at %s:%d" % (f.file, f.line)
        parts.append("Location: %s" % loc)
        parts.append("Address: %s" % f.address)
    if stop.breakpoint_number is not None:
        parts.append("Breakpoint: #%d" % stop.breakpoint_number)
    if stop.signal_name:
        parts.append("Signal: %s (%s)" % (stop.signal_name,
                                          stop.signal_meaning or ""))
    return "\n".join(parts)


def _format_breakpoint(bp):
    parts = ["Breakpoint #%d: %s" % (bp.number, bp.location)]
    if bp.file and bp.line:
        parts.append("  File: %s:%d" % (bp.file, bp.line))
    if bp.condition:
        parts.append("  Condition: %s" % bp.condition)
    parts.append("  Enabled: %s" % bp.enabled)
    return "\n".join(parts)


def _format_frame(frame):
    loc = frame.function or "??"
    if frame.file and frame.line:
        loc += " at %s:%d" % (frame.file, frame.line)
    return "#%d  %s  (%s)" % (frame.level, frame.address, loc)


# --- Session Lifecycle Tools ---

@mcp.tool()
def rr_record(command: list[str], working_directory: str = None,
              env: dict[str, str] = None,
              trace_dir: str = None) -> str:
    """Record a command with rr. Returns trace directory path.

    Args:
        command: Command and arguments to record (e.g. ["./my_test"]).
        working_directory: Working directory for the recorded process.
        env: Optional extra environment variables for the recorded process.
        trace_dir: Output trace directory. If omitted, rr uses its default (~/.local/share/rr/).
    """
    try:
        trace_dir, exit_code, stdout, stderr = rr_record_cmd(
            command, working_directory=working_directory, env=env,
            trace_dir=trace_dir)
        parts = ["Recording complete."]
        if trace_dir:
            parts.append("Trace directory: %s" % trace_dir)
        parts.append("Exit code: %d" % exit_code)
        if stdout.strip():
            parts.append("--- stdout ---\n%s" % stdout.strip())
        if stderr.strip():
            parts.append("--- stderr ---\n%s" % stderr.strip())
        return "\n".join(parts)
    except RrError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_replay_start(trace_dir: str = None, pid: int = None) -> str:
    """Start a replay session. Launches rr gdbserver and connects GDB/MI.

    Args:
        trace_dir: Path to rr trace directory. If omitted, uses the latest trace.
        pid: PID of a specific subprocess to replay. Use rr_ps to list available processes.
    """
    global _replay_server, _gdb_session
    try:
        if _gdb_session is not None:
            return "Error: A replay session is already active. Call rr_replay_stop first."

        server = ReplayServer(trace_dir=trace_dir, pid=pid)
        server.start()

        session = GdbSession()
        session.start()
        session.connect("localhost", server.port)

        _replay_server = server
        _gdb_session = session
        return "Replay session started on port %d. Program is paused at start." % server.port
    except (RrError, GdbSessionError) as e:
        # Clean up on failure
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        if server is not None:
            try:
                server.stop()
            except Exception:
                pass
        return "Error: %s" % e


@mcp.tool()
def rr_replay_stop() -> str:
    """Stop the current replay session and clean up."""
    if _gdb_session is None and _replay_server is None:
        return "No active replay session."
    _cleanup()
    return "Replay session stopped."


@mcp.tool()
def rr_list_recordings(trace_base_dir: str = None) -> str:
    """List available rr trace recordings.

    Args:
        trace_base_dir: Base directory for traces. Defaults to ~/.local/share/rr.
    """
    recordings = rr_list(trace_base_dir=trace_base_dir)
    if not recordings:
        return "No recordings found."
    return "Available recordings:\n" + "\n".join("  - %s" % r for r in recordings)


@mcp.tool()
def rr_ps(trace_dir: str) -> str:
    """List processes in an rr trace recording.

    Args:
        trace_dir: Path to rr trace directory.
    """
    try:
        processes = rr_ps_cmd(trace_dir)
        if not processes:
            return "No processes found in recording."
        lines = ["PID\tPPID\tEXIT\tCMD"]
        for p in processes:
            ppid = str(p.ppid) if p.ppid is not None else "--"
            exit_code = str(p.exit_code) if p.exit_code is not None else "--"
            cmd = p.cmd or ""
            lines.append("%d\t%s\t%s\t%s" % (p.pid, ppid, exit_code, cmd))
        return "\n".join(lines)
    except RrError as e:
        return "Error: %s" % e


# --- Breakpoint Tools ---

@mcp.tool()
def rr_breakpoint_set(location: str, condition: str = None,
                      temporary: bool = False) -> str:
    """Set a breakpoint at a function, file:line, or address.

    Args:
        location: Breakpoint location (e.g. "main", "foo.c:42", "*0x400500").
        condition: Optional condition expression (e.g. "i > 10").
        temporary: If true, breakpoint is deleted after first hit.
    """
    try:
        session = _require_session()
        bp = session.breakpoint_set(location, condition=condition, temporary=temporary)
        return _format_breakpoint(bp)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_breakpoint_remove(breakpoint_number: int) -> str:
    """Remove a breakpoint by its number.

    Args:
        breakpoint_number: The breakpoint number to remove.
    """
    try:
        session = _require_session()
        session.breakpoint_delete(breakpoint_number)
        return "Breakpoint #%d removed." % breakpoint_number
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_breakpoint_list() -> str:
    """List all breakpoints."""
    try:
        session = _require_session()
        bps = session.breakpoint_list()
        if not bps:
            return "No breakpoints set."
        return "\n\n".join(_format_breakpoint(bp) for bp in bps)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_watchpoint_set(expression: str,
                      access_type: str = "write") -> str:
    """Set a hardware watchpoint on a variable or expression.

    Args:
        expression: Expression to watch (e.g. "my_var", "*0x601050").
        access_type: One of "write", "read", or "access".
    """
    try:
        session = _require_session()
        wp = session.watchpoint_set(expression, access_type=access_type)
        if wp:
            return _format_breakpoint(wp)
        return "Watchpoint set on %s (%s)" % (expression, access_type)
    except GdbSessionError as e:
        return "Error: %s" % e


# --- Execution Control Tools ---

@mcp.tool()
def rr_continue(reverse: bool = False) -> str:
    """Continue execution forward or backward until breakpoint/signal/end.

    Args:
        reverse: If true, continue backward (reverse execution).
    """
    try:
        session = _require_session()
        stop = session.continue_execution(reverse=reverse)
        return _format_stop_event(stop)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_step(count: int = 1, reverse: bool = False) -> str:
    """Step into (source-level) forward or reverse.

    Args:
        count: Number of steps (forward only).
        reverse: If true, step backward.
    """
    try:
        session = _require_session()
        stop = session.step(count=count, reverse=reverse)
        return _format_stop_event(stop)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_next(count: int = 1, reverse: bool = False) -> str:
    """Step over (source-level) forward or reverse.

    Args:
        count: Number of steps (forward only).
        reverse: If true, step backward.
    """
    try:
        session = _require_session()
        stop = session.next(count=count, reverse=reverse)
        return _format_stop_event(stop)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_finish(reverse: bool = False) -> str:
    """Run to function return (or to call site if reverse).

    Args:
        reverse: If true, run backward to the call site.
    """
    try:
        session = _require_session()
        stop = session.finish(reverse=reverse)
        return _format_stop_event(stop)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_run_to_event(event_number: int) -> str:
    """Jump to a specific rr event number.

    Args:
        event_number: The rr event number to seek to.
    """
    try:
        session = _require_session()
        stop = session.run_to_event(event_number)
        return _format_stop_event(stop)
    except GdbSessionError as e:
        return "Error: %s" % e


# --- State Inspection Tools ---

@mcp.tool()
def rr_backtrace(max_depth: int = None) -> str:
    """Get the call stack (backtrace).

    Args:
        max_depth: Maximum number of frames to return.
    """
    try:
        session = _require_session()
        frames = session.backtrace(max_depth=max_depth)
        if not frames:
            return "No stack frames."
        return "\n".join(_format_frame(f) for f in frames)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_evaluate(expression: str) -> str:
    """Evaluate a C/C++ expression in the current context.

    Args:
        expression: Expression to evaluate (e.g. "x + 1", "sizeof(struct foo)").
    """
    try:
        session = _require_session()
        value = session.evaluate(expression)
        return "%s = %s" % (expression, value)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_locals() -> str:
    """List local variables with their current values."""
    try:
        session = _require_session()
        variables = session.locals()
        if not variables:
            return "No local variables."
        lines = []
        for v in variables:
            line = "%s = %s" % (v.name, v.value)
            if v.type:
                line += "  (%s)" % v.type
            lines.append(line)
        return "\n".join(lines)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_read_memory(address: str, count: int = 64) -> str:
    """Read raw memory bytes at an address.

    Args:
        address: Memory address to read (e.g. "0x7ffd1234").
        count: Number of bytes to read (default 64).
    """
    try:
        session = _require_session()
        hex_bytes = session.read_memory(address, count=count)
        return "Memory at %s (%d bytes): %s" % (address, count, hex_bytes)
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_registers(register_names: list[str] = None) -> str:
    """Read CPU registers.

    Args:
        register_names: Specific register names to read. If omitted, reads all.
    """
    try:
        session = _require_session()
        regs = session.registers(register_names=register_names)
        if not regs:
            return "No register values."
        return "\n".join("  %s = %s" % (k, v) for k, v in regs.items())
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_source_lines(file: str = None, line: int = None,
                    count: int = 10) -> str:
    """List source code around current position or a specific location.

    Args:
        file: Source file path. If omitted, uses current position.
        line: Line number. If omitted, uses current position.
        count: Number of lines to show (default 10).
    """
    try:
        session = _require_session()
        src = session.source_lines(file=file, line=line, count=count)
        return src if src else "No source available."
    except GdbSessionError as e:
        return "Error: %s" % e


# --- Checkpoint Tools ---

@mcp.tool()
def rr_checkpoint_save() -> str:
    """Save a checkpoint at the current position. Returns checkpoint info."""
    try:
        session = _require_session()
        output = session.checkpoint_save()
        return output if output else "Checkpoint saved."
    except GdbSessionError as e:
        return "Error: %s" % e


@mcp.tool()
def rr_checkpoint_restore(checkpoint_id: int) -> str:
    """Restore to a previously saved checkpoint.

    Args:
        checkpoint_id: The checkpoint ID to restore.
    """
    try:
        session = _require_session()
        result = session.checkpoint_restore(checkpoint_id)
        if hasattr(result, "reason"):
            return _format_stop_event(result)
        return str(result) if result else "Checkpoint %d restored." % checkpoint_id
    except GdbSessionError as e:
        return "Error: %s" % e


def main():
    mcp.run(transport="stdio")
