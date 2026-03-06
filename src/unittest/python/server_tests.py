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

import unittest
from unittest.mock import patch, MagicMock

from mcp.server.fastmcp.exceptions import ToolError

from karellen_rr_mcp.gdb_session import GdbSessionError
from karellen_rr_mcp.rr_manager import RrError
from karellen_rr_mcp.types import (
    Breakpoint, Frame, Variable, StopEvent, ProcessInfo,
    RecordResult, EvalResult, MemoryResult, ReplayStatus,
    StringResult, IntResult, RegisterValues,
)
import karellen_rr_mcp.server as server


class TagErrorsDecoratorTests(unittest.TestCase):
    def test_gdb_error_tagged(self):
        @server._tag_errors
        def fail():
            raise GdbSessionError("bad gdb")
        with self.assertRaises(ToolError) as ctx:
            fail()
        self.assertTrue(str(ctx.exception).startswith("gdb:"))

    def test_rr_error_tagged(self):
        @server._tag_errors
        def fail():
            raise RrError("bad rr")
        with self.assertRaises(ToolError) as ctx:
            fail()
        self.assertTrue(str(ctx.exception).startswith("rr:"))

    def test_unexpected_error_tagged_with_type_and_traceback(self):
        @server._tag_errors
        def fail():
            raise ValueError("bad value")
        with self.assertRaises(ToolError) as ctx:
            fail()
        msg = str(ctx.exception)
        self.assertTrue(msg.startswith("internal:"))
        self.assertIn("ValueError", msg)
        self.assertIn("bad value", msg)
        self.assertIn("in fail", msg)

    def test_unexpected_key_error_tagged_with_type_and_traceback(self):
        @server._tag_errors
        def fail():
            raise KeyError("missing")
        with self.assertRaises(ToolError) as ctx:
            fail()
        msg = str(ctx.exception)
        self.assertIn("internal:", msg)
        self.assertIn("KeyError", msg)
        self.assertIn("in fail", msg)

    def test_tool_error_passes_through(self):
        @server._tag_errors
        def fail():
            raise ToolError("already tagged")
        with self.assertRaises(ToolError) as ctx:
            fail()
        self.assertEqual(str(ctx.exception), "already tagged")

    def test_no_error_passes_through(self):
        @server._tag_errors
        def ok():
            return "fine"
        self.assertEqual(ok(), "fine")


class RequireSessionTests(unittest.TestCase):
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    def test_no_session_raises(self):
        with self.assertRaises(GdbSessionError):
            server._require_session()

    def test_disconnected_session_raises(self):
        mock_session = MagicMock()
        mock_session.is_connected.return_value = False
        server._gdb_session = mock_session
        with self.assertRaises(GdbSessionError):
            server._require_session()

    def test_connected_session_returns(self):
        mock_session = MagicMock()
        mock_session.is_connected.return_value = True
        server._gdb_session = mock_session
        self.assertIs(server._require_session(), mock_session)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class RequireStopTests(unittest.TestCase):
    def test_none_raises(self):
        with self.assertRaises(GdbSessionError):
            server._require_stop(None)

    def test_stop_event_passes_through(self):
        stop = StopEvent(reason="breakpoint-hit")
        self.assertIs(server._require_stop(stop), stop)


class RrRecordToolTests(unittest.TestCase):
    @patch("karellen_rr_mcp.server.rr_record_cmd")
    def test_record_success(self, mock_record):
        mock_record.return_value = ("/traces/test-0", 0, "output", "stderr")
        result = server.rr_record(["./test"])
        self.assertIsInstance(result, RecordResult)
        self.assertEqual(result.trace_dir, "/traces/test-0")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "output")
        self.assertEqual(result.stderr, "stderr")

    @patch("karellen_rr_mcp.server.rr_record_cmd")
    def test_record_nonzero_exit(self, mock_record):
        mock_record.return_value = ("/traces/test-1", 1, "", "error output")
        result = server.rr_record(["./test"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, "error output")

    @patch("karellen_rr_mcp.server.rr_record_cmd")
    def test_record_error(self, mock_record):
        mock_record.side_effect = RrError("rr not installed")
        with self.assertRaises(ToolError) as ctx:
            server.rr_record(["./test"])
        self.assertIn("rr:", str(ctx.exception))
        self.assertIn("rr not installed", str(ctx.exception))


class RrReplayStartToolTests(unittest.TestCase):
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    @patch("karellen_rr_mcp.server.GdbSession")
    @patch("karellen_rr_mcp.server.ReplayServer")
    def test_replay_start_success(self, mock_replay_cls, mock_gdb_cls):
        mock_server = MagicMock()
        mock_server.port = 12345
        mock_replay_cls.return_value = mock_server
        mock_session = MagicMock()
        mock_gdb_cls.return_value = mock_session

        result = server.rr_replay_start("/traces/test-0")
        self.assertIsInstance(result, ReplayStatus)
        self.assertEqual(result.port, 12345)
        mock_server.start.assert_called_once()
        mock_session.start.assert_called_once()
        mock_session.connect.assert_called_once_with("localhost", 12345)

    def test_replay_start_already_active(self):
        server._gdb_session = MagicMock()
        with self.assertRaises(ToolError) as ctx:
            server.rr_replay_start()
        self.assertIn("already active", str(ctx.exception))

    @patch("karellen_rr_mcp.server.GdbSession")
    @patch("karellen_rr_mcp.server.ReplayServer")
    def test_replay_start_connect_failure_cleans_up(self, mock_replay_cls, mock_gdb_cls):
        mock_server = MagicMock()
        mock_server.port = 12345
        mock_replay_cls.return_value = mock_server
        mock_session = MagicMock()
        mock_session.connect.side_effect = GdbSessionError("connection refused")
        mock_gdb_cls.return_value = mock_session

        with self.assertRaises(ToolError):
            server.rr_replay_start("/traces/test-0")
        mock_session.close.assert_called_once()
        mock_server.stop.assert_called_once()

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class RrReplayStopToolTests(unittest.TestCase):
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    def test_stop_no_session(self):
        result = server.rr_replay_stop()
        self.assertIsInstance(result, StringResult)
        self.assertIn("No active", result.result)

    def test_stop_active_session(self):
        server._gdb_session = MagicMock()
        server._replay_server = MagicMock()
        result = server.rr_replay_stop()
        self.assertIsInstance(result, StringResult)
        self.assertIn("stopped", result.result)
        self.assertIsNone(server._gdb_session)
        self.assertIsNone(server._replay_server)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class RrListRecordingsToolTests(unittest.TestCase):
    @patch("karellen_rr_mcp.server.rr_list")
    def test_no_recordings(self, mock_list):
        mock_list.return_value = []
        result = server.rr_list_recordings()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    @patch("karellen_rr_mcp.server.rr_list")
    def test_with_recordings(self, mock_list):
        mock_list.return_value = ["/traces/test-0", "/traces/test-1"]
        result = server.rr_list_recordings()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "/traces/test-0")
        self.assertEqual(result[1], "/traces/test-1")


class RrPsToolTests(unittest.TestCase):
    @patch("karellen_rr_mcp.server.rr_ps_cmd")
    def test_with_processes(self, mock_ps):
        mock_ps.return_value = [
            ProcessInfo(pid=100, ppid=None, exit_code=0, cmd="./test"),
            ProcessInfo(pid=200, ppid=100, exit_code=-11, cmd="./child"),
        ]
        result = server.rr_ps("/traces/test-0")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].pid, 100)
        self.assertEqual(result[1].exit_code, -11)

    @patch("karellen_rr_mcp.server.rr_ps_cmd")
    def test_error(self, mock_ps):
        mock_ps.side_effect = RrError("rr ps failed")
        with self.assertRaises(ToolError) as ctx:
            server.rr_ps("/nonexistent")
        self.assertIn("rr:", str(ctx.exception))


class RrReplayStartWithPidTests(unittest.TestCase):
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    @patch("karellen_rr_mcp.server.GdbSession")
    @patch("karellen_rr_mcp.server.ReplayServer")
    def test_replay_start_with_pid(self, mock_replay_cls, mock_gdb_cls):
        mock_server = MagicMock()
        mock_server.port = 12345
        mock_replay_cls.return_value = mock_server
        mock_session = MagicMock()
        mock_gdb_cls.return_value = mock_session

        result = server.rr_replay_start("/traces/test-0", pid=820291)
        self.assertIsInstance(result, ReplayStatus)
        self.assertEqual(result.port, 12345)
        mock_replay_cls.assert_called_once_with(trace_dir="/traces/test-0", pid=820291)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class BreakpointToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_set_breakpoint(self):
        bp = Breakpoint(number=1, type="breakpoint", location="main",
                        file="test.c", line=5)
        self.mock_session.breakpoint_set.return_value = bp
        result = server.rr_breakpoint_set("main")
        self.assertIsInstance(result, Breakpoint)
        self.assertEqual(result.number, 1)
        self.assertEqual(result.location, "main")

    def test_remove_breakpoint(self):
        result = server.rr_breakpoint_remove(1)
        self.assertIsInstance(result, IntResult)
        self.assertEqual(result.result, 1)
        self.mock_session.breakpoint_delete.assert_called_once_with(1)

    def test_list_breakpoints(self):
        bps = [
            Breakpoint(number=1, type="breakpoint", location="main"),
            Breakpoint(number=2, type="breakpoint", location="foo"),
        ]
        self.mock_session.breakpoint_list.return_value = bps
        result = server.rr_breakpoint_list()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].number, 1)
        self.assertEqual(result[1].number, 2)

    def test_set_watchpoint(self):
        wp = Breakpoint(number=3, type="watchpoint", location="x")
        self.mock_session.watchpoint_set.return_value = wp
        result = server.rr_watchpoint_set("x")
        self.assertIsInstance(result, Breakpoint)
        self.assertEqual(result.number, 3)

    def test_set_watchpoint_none_raises(self):
        self.mock_session.watchpoint_set.return_value = None
        with self.assertRaises(ToolError) as ctx:
            server.rr_watchpoint_set("x")
        self.assertIn("gdb:", str(ctx.exception))

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class ExecutionToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session
        self.stop = StopEvent(
            reason="breakpoint-hit",
            frame=Frame(level=0, address="0x400500", function="main"))

    def test_continue(self):
        self.mock_session.continue_execution.return_value = self.stop
        result = server.rr_continue()
        self.assertIsInstance(result, StopEvent)
        self.assertEqual(result.reason, "breakpoint-hit")

    def test_continue_reverse(self):
        self.mock_session.continue_execution.return_value = self.stop
        server.rr_continue(reverse=True)
        self.mock_session.continue_execution.assert_called_once_with(reverse=True)

    def test_continue_none_raises(self):
        self.mock_session.continue_execution.return_value = None
        with self.assertRaises(ToolError) as ctx:
            server.rr_continue()
        self.assertIn("gdb:", str(ctx.exception))

    def test_step(self):
        self.mock_session.step.return_value = self.stop
        result = server.rr_step()
        self.assertIsInstance(result, StopEvent)
        self.assertEqual(result.reason, "breakpoint-hit")

    def test_next(self):
        self.mock_session.next.return_value = self.stop
        server.rr_next(count=2)
        self.mock_session.next.assert_called_once_with(count=2, reverse=False)

    def test_finish(self):
        self.mock_session.finish.return_value = self.stop
        result = server.rr_finish()
        self.assertIsInstance(result, StopEvent)

    def test_run_to_event(self):
        self.mock_session.run_to_event.return_value = self.stop
        result = server.rr_run_to_event(42)
        self.assertIsInstance(result, StopEvent)
        self.mock_session.run_to_event.assert_called_once_with(42)

    def test_continue_error(self):
        self.mock_session.continue_execution.side_effect = GdbSessionError("failed")
        with self.assertRaises(ToolError) as ctx:
            server.rr_continue()
        self.assertIn("gdb:", str(ctx.exception))

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class InspectionToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_backtrace(self):
        frames = [
            Frame(level=0, address="0x500", function="bar", file="b.c", line=3),
            Frame(level=1, address="0x600", function="main", file="a.c", line=10),
        ]
        self.mock_session.backtrace.return_value = frames
        result = server.rr_backtrace()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].function, "bar")
        self.assertEqual(result[1].function, "main")

    def test_evaluate(self):
        self.mock_session.evaluate.return_value = "42"
        result = server.rr_evaluate("x + 1")
        self.assertIsInstance(result, EvalResult)
        self.assertEqual(result.expression, "x + 1")
        self.assertEqual(result.value, "42")

    def test_locals(self):
        variables = [
            Variable(name="x", value="10", type="int"),
            Variable(name="s", value='"hello"', type="char *"),
        ]
        self.mock_session.locals.return_value = variables
        result = server.rr_locals()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "x")
        self.assertEqual(result[1].name, "s")

    def test_read_memory(self):
        self.mock_session.read_memory.return_value = "deadbeef"
        result = server.rr_read_memory("0x1000", count=16)
        self.assertIsInstance(result, MemoryResult)
        self.assertEqual(result.address, "0x1000")
        self.assertEqual(result.count, 16)
        self.assertEqual(result.contents, "deadbeef")

    def test_registers(self):
        self.mock_session.registers.return_value = {"0": "0x1", "1": "0x2"}
        result = server.rr_registers()
        self.assertIsInstance(result, RegisterValues)
        self.assertEqual(result.registers["0"], "0x1")
        self.assertEqual(result.registers["1"], "0x2")

    def test_source_lines(self):
        self.mock_session.source_lines.return_value = "1\tint main() {\n2\t  return 0;\n"
        result = server.rr_source_lines()
        self.assertIsInstance(result, StringResult)
        self.assertIn("int main()", result.result)

    def test_source_lines_empty(self):
        self.mock_session.source_lines.return_value = ""
        result = server.rr_source_lines()
        self.assertIsInstance(result, StringResult)
        self.assertIn("No source", result.result)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class CheckpointToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_checkpoint_save(self):
        self.mock_session.checkpoint_save.return_value = "checkpoint 1 at event 42"
        result = server.rr_checkpoint_save()
        self.assertIsInstance(result, StringResult)
        self.assertIn("checkpoint 1", result.result)

    def test_checkpoint_save_empty(self):
        self.mock_session.checkpoint_save.return_value = ""
        result = server.rr_checkpoint_save()
        self.assertIsInstance(result, StringResult)
        self.assertIn("Checkpoint saved", result.result)

    def test_checkpoint_restore_stop_event(self):
        stop = StopEvent(reason="breakpoint-hit",
                         frame=Frame(level=0, address="0x500", function="main"))
        self.mock_session.checkpoint_restore.return_value = stop
        result = server.rr_checkpoint_restore(1)
        self.assertIsInstance(result, StopEvent)
        self.assertEqual(result.reason, "breakpoint-hit")

    def test_checkpoint_restore_no_stop_raises(self):
        self.mock_session.checkpoint_restore.return_value = "some string"
        with self.assertRaises(ToolError) as ctx:
            server.rr_checkpoint_restore(1)
        self.assertIn("gdb:", str(ctx.exception))

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class ThreadToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_thread_list(self):
        from karellen_rr_mcp.types import ThreadInfo
        threads = [
            ThreadInfo(id="1", name="main", state="stopped", current=True,
                       frame=Frame(level=0, address="0x500", function="foo")),
            ThreadInfo(id="2", name="worker", state="stopped", current=False),
        ]
        self.mock_session.thread_info.return_value = threads
        result = server.rr_thread_list()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "1")
        self.assertTrue(result[0].current)
        self.assertFalse(result[1].current)

    def test_thread_select(self):
        result = server.rr_thread_select("2")
        self.assertIsInstance(result, IntResult)
        self.assertEqual(result.result, 2)
        self.mock_session.thread_select.assert_called_once_with("2")

    def test_select_frame(self):
        result = server.rr_select_frame(3)
        self.assertIsInstance(result, IntResult)
        self.assertEqual(result.result, 3)
        self.mock_session.select_frame.assert_called_once_with(3)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class NoSessionToolTests(unittest.TestCase):
    """Verify tools raise ToolError when no session is active."""
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    def test_breakpoint_set_no_session(self):
        with self.assertRaises(ToolError) as ctx:
            server.rr_breakpoint_set("main")
        self.assertIn("gdb:", str(ctx.exception))

    def test_continue_no_session(self):
        with self.assertRaises(ToolError):
            server.rr_continue()

    def test_backtrace_no_session(self):
        with self.assertRaises(ToolError):
            server.rr_backtrace()

    def test_evaluate_no_session(self):
        with self.assertRaises(ToolError):
            server.rr_evaluate("x")
