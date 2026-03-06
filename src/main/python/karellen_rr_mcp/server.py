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
import functools
import logging
import signal
import traceback

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from karellen_rr_mcp.gdb_session import GdbSession, GdbSessionError
from karellen_rr_mcp.rr_manager import (
    record as rr_record_cmd,
    list_recordings as rr_list,
    list_processes as rr_ps_cmd,
    trace_info as rr_trace_info_cmd,
    remove_recording as rr_rm_cmd,
    ReplayServer, RrError,
)
from karellen_rr_mcp.types import (
    Breakpoint, Frame, StopEvent, Variable, ThreadInfo,
    ProcessInfo, RecordResult, EvalResult, MemoryResult,
    ReplayStatus, StringResult, IntResult, RegisterValues,
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


def _tag_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GdbSessionError as e:
            raise ToolError("gdb: %s" % e) from e
        except RrError as e:
            raise ToolError("rr: %s" % e) from e
        except ToolError:
            raise
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            tb_lines = ["%s:%d in %s" % (f.filename, f.lineno, f.name) for f in tb[-3:]]
            raise ToolError("internal: %s: %s\n  %s" % (
                type(e).__name__, e, "\n  ".join(tb_lines))) from e
    return wrapper


def _require_stop(stop):
    if stop is None:
        raise GdbSessionError("No stop event received")
    return stop


# --- Session Lifecycle Tools ---

@mcp.tool()
@_tag_errors
def rr_record(command: list[str], working_directory: str = None,
              env: dict[str, str] = None,
              trace_dir: str = None) -> RecordResult:
    """Record a command with rr. Returns trace directory path.

    Args:
        command: Command and arguments to record (e.g. ["./my_test"]).
        working_directory: Working directory for the recorded process.
        env: Optional extra environment variables for the recorded process.
        trace_dir: Output trace directory. If omitted, rr uses its default (~/.local/share/rr/).
    """
    trace_dir, exit_code, stdout, stderr = rr_record_cmd(
        command, working_directory=working_directory, env=env,
        trace_dir=trace_dir)
    return RecordResult(trace_dir=trace_dir, exit_code=exit_code,
                        stdout=stdout, stderr=stderr)


@mcp.tool()
@_tag_errors
def rr_replay_start(trace_dir: str = None, pid: int = None) -> ReplayStatus:
    """Start a replay session. Launches rr gdbserver and connects GDB/MI.

    Args:
        trace_dir: Path to rr trace directory. If omitted, uses the latest trace.
        pid: PID of a specific subprocess to replay. Use rr_ps to list available processes.
    """
    global _replay_server, _gdb_session
    if _gdb_session is not None:
        raise ToolError("gdb: A replay session is already active. Call rr_replay_stop first.")

    server = ReplayServer(trace_dir=trace_dir, pid=pid)
    session = None
    try:
        server.start()

        session = GdbSession()
        session.start()
        session.connect("localhost", server.port)

        _replay_server = server
        _gdb_session = session
        return ReplayStatus(port=server.port, message="Program is paused at start.")
    except (RrError, GdbSessionError):
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        try:
            server.stop()
        except Exception:
            pass
        raise


@mcp.tool()
@_tag_errors
def rr_replay_stop() -> StringResult:
    """Stop the current replay session and clean up."""
    if _gdb_session is None and _replay_server is None:
        return StringResult(result="No active replay session.")
    _cleanup()
    return StringResult(result="Replay session stopped.")


@mcp.tool()
@_tag_errors
def rr_list_recordings(trace_base_dir: str = None) -> list[str]:
    """List available rr trace recordings.

    Args:
        trace_base_dir: Base directory for traces. Defaults to ~/.local/share/rr.
    """
    return rr_list(trace_base_dir=trace_base_dir)


@mcp.tool()
@_tag_errors
def rr_ps(trace_dir: str) -> list[ProcessInfo]:
    """List processes in an rr trace recording.

    Args:
        trace_dir: Path to rr trace directory.
    """
    return rr_ps_cmd(trace_dir)


@mcp.tool()
@_tag_errors
def rr_traceinfo(trace_dir: str) -> StringResult:
    """Get trace metadata (header info in JSON format).

    Args:
        trace_dir: Path to rr trace directory.
    """
    return StringResult(result=rr_trace_info_cmd(trace_dir))


@mcp.tool()
@_tag_errors
def rr_rm(trace_dir: str) -> StringResult:
    """Remove an rr trace recording.

    Args:
        trace_dir: Path to rr trace directory to remove.
    """
    rr_rm_cmd(trace_dir)
    return StringResult(result="Trace removed: %s" % trace_dir)


@mcp.tool()
@_tag_errors
def rr_when() -> StringResult:
    """Get the current rr event number. Useful for knowing your position in the trace."""
    session = _require_session()
    output = session.rr_when()
    return StringResult(result=output if output else "Unable to determine current event.")


# --- Breakpoint Tools ---

@mcp.tool()
@_tag_errors
def rr_breakpoint_set(location: str, condition: str = None,
                      temporary: bool = False) -> Breakpoint:
    """Set a breakpoint at a function, file:line, or address.

    Args:
        location: Breakpoint location (e.g. "main", "foo.c:42", "*0x400500").
        condition: Optional condition expression (e.g. "i > 10").
        temporary: If true, breakpoint is deleted after first hit.
    """
    session = _require_session()
    return session.breakpoint_set(location, condition=condition, temporary=temporary)


@mcp.tool()
@_tag_errors
def rr_breakpoint_remove(breakpoint_number: int) -> IntResult:
    """Remove a breakpoint by its number.

    Args:
        breakpoint_number: The breakpoint number to remove.
    """
    session = _require_session()
    session.breakpoint_delete(breakpoint_number)
    return IntResult(result=breakpoint_number)


@mcp.tool()
@_tag_errors
def rr_breakpoint_list() -> list[Breakpoint]:
    """List all breakpoints."""
    session = _require_session()
    return session.breakpoint_list()


@mcp.tool()
@_tag_errors
def rr_watchpoint_set(expression: str,
                      access_type: str = "write") -> Breakpoint:
    """Set a hardware watchpoint on a variable or expression.

    Args:
        expression: Expression to watch (e.g. "my_var", "*0x601050").
        access_type: One of "write", "read", or "access".
    """
    session = _require_session()
    wp = session.watchpoint_set(expression, access_type=access_type)
    if wp is None:
        raise GdbSessionError("Failed to parse watchpoint response")
    return wp


# --- Execution Control Tools ---

@mcp.tool()
@_tag_errors
def rr_continue(reverse: bool = False) -> StopEvent:
    """Continue execution forward or backward until breakpoint/signal/end.

    Args:
        reverse: If true, continue backward (reverse execution).
    """
    session = _require_session()
    return _require_stop(session.continue_execution(reverse=reverse))


@mcp.tool()
@_tag_errors
def rr_step(count: int = 1, reverse: bool = False) -> StopEvent:
    """Step into (source-level) forward or reverse.

    Args:
        count: Number of steps (forward only).
        reverse: If true, step backward.
    """
    session = _require_session()
    return _require_stop(session.step(count=count, reverse=reverse))


@mcp.tool()
@_tag_errors
def rr_next(count: int = 1, reverse: bool = False) -> StopEvent:
    """Step over (source-level) forward or reverse.

    Args:
        count: Number of steps (forward only).
        reverse: If true, step backward.
    """
    session = _require_session()
    return _require_stop(session.next(count=count, reverse=reverse))


@mcp.tool()
@_tag_errors
def rr_finish(reverse: bool = False) -> StopEvent:
    """Run to function return (or to call site if reverse).

    Args:
        reverse: If true, run backward to the call site.
    """
    session = _require_session()
    return _require_stop(session.finish(reverse=reverse))


@mcp.tool()
@_tag_errors
def rr_run_to_event(event_number: int) -> StopEvent:
    """Jump to a specific rr event number.

    Args:
        event_number: The rr event number to seek to.
    """
    session = _require_session()
    return _require_stop(session.run_to_event(event_number))


# --- Thread and Frame Tools ---

@mcp.tool()
@_tag_errors
def rr_thread_list() -> list[ThreadInfo]:
    """List all threads in the replayed process with their current state and location."""
    session = _require_session()
    return session.thread_info()


@mcp.tool()
@_tag_errors
def rr_thread_select(thread_id: str) -> IntResult:
    """Switch to a different thread.

    Args:
        thread_id: Thread ID to switch to (from rr_thread_list).
    """
    session = _require_session()
    session.thread_select(thread_id)
    return IntResult(result=int(thread_id))


@mcp.tool()
@_tag_errors
def rr_select_frame(frame_level: int) -> IntResult:
    """Select a stack frame for inspection. After selecting, rr_locals and rr_evaluate
    operate in the selected frame's context.

    Args:
        frame_level: Frame number from rr_backtrace (0 = innermost/current).
    """
    session = _require_session()
    session.select_frame(frame_level)
    return IntResult(result=frame_level)


# --- State Inspection Tools ---

@mcp.tool()
@_tag_errors
def rr_backtrace(max_depth: int = None) -> list[Frame]:
    """Get the call stack (backtrace).

    Args:
        max_depth: Maximum number of frames to return.
    """
    session = _require_session()
    return session.backtrace(max_depth=max_depth)


@mcp.tool()
@_tag_errors
def rr_evaluate(expression: str) -> EvalResult:
    """Evaluate a C/C++ expression in the current context.

    Args:
        expression: Expression to evaluate (e.g. "x + 1", "sizeof(struct foo)").
    """
    session = _require_session()
    value = session.evaluate(expression)
    return EvalResult(expression=expression, value=value)


@mcp.tool()
@_tag_errors
def rr_locals() -> list[Variable]:
    """List local variables with their current values."""
    session = _require_session()
    return session.locals()


@mcp.tool()
@_tag_errors
def rr_read_memory(address: str, count: int = 64) -> MemoryResult:
    """Read raw memory bytes at an address.

    Args:
        address: Memory address to read (e.g. "0x7ffd1234").
        count: Number of bytes to read (default 64).
    """
    session = _require_session()
    hex_bytes = session.read_memory(address, count=count)
    return MemoryResult(address=address, count=count, contents=hex_bytes)


@mcp.tool()
@_tag_errors
def rr_registers(register_names: list[str] = None) -> RegisterValues:
    """Read CPU registers.

    Args:
        register_names: Specific register names to read. If omitted, reads all.
    """
    session = _require_session()
    return RegisterValues(registers=session.registers(register_names=register_names))


@mcp.tool()
@_tag_errors
def rr_source_lines(file: str = None, line: int = None,
                    count: int = 10) -> StringResult:
    """List source code around current position or a specific location.

    Args:
        file: Source file path. If omitted, uses current position.
        line: Line number. If omitted, uses current position.
        count: Number of lines to show (default 10).
    """
    session = _require_session()
    src = session.source_lines(file=file, line=line, count=count)
    return StringResult(result=src if src else "No source available.")


# --- Checkpoint Tools ---

@mcp.tool()
@_tag_errors
def rr_checkpoint_save() -> StringResult:
    """Save a checkpoint at the current position. Returns checkpoint info."""
    session = _require_session()
    output = session.checkpoint_save()
    return StringResult(result=output if output else "Checkpoint saved.")


@mcp.tool()
@_tag_errors
def rr_checkpoint_restore(checkpoint_id: int) -> StopEvent:
    """Restore to a previously saved checkpoint.

    Args:
        checkpoint_id: The checkpoint ID to restore.
    """
    session = _require_session()
    result = session.checkpoint_restore(checkpoint_id)
    if isinstance(result, StopEvent):
        return result
    raise GdbSessionError("No stop event after checkpoint restore")


def main():
    mcp.run(transport="stdio")
