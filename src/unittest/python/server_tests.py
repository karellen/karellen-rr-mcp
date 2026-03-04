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

from karellen_rr_mcp.gdb_session import GdbSessionError
from karellen_rr_mcp.rr_manager import RrError
from karellen_rr_mcp.types import Breakpoint, Frame, Variable, StopEvent
import karellen_rr_mcp.server as server


class FormatStopEventTests(unittest.TestCase):
    def test_format_none(self):
        result = server._format_stop_event(None)
        self.assertIn("no details", result)

    def test_format_breakpoint_hit(self):
        stop = StopEvent(
            reason="breakpoint-hit",
            frame=Frame(level=0, address="0x400500", function="main",
                        file="test.c", line=10),
            breakpoint_number=1,
        )
        result = server._format_stop_event(stop)
        self.assertIn("breakpoint-hit", result)
        self.assertIn("main", result)
        self.assertIn("test.c:10", result)
        self.assertIn("#1", result)

    def test_format_signal(self):
        stop = StopEvent(
            reason="signal-received",
            frame=Frame(level=0, address="0x400500"),
            signal_name="SIGSEGV",
            signal_meaning="Segmentation fault",
        )
        result = server._format_stop_event(stop)
        self.assertIn("SIGSEGV", result)
        self.assertIn("Segmentation fault", result)


class FormatBreakpointTests(unittest.TestCase):
    def test_format_full(self):
        bp = Breakpoint(number=1, type="breakpoint", location="main",
                        file="test.c", line=5, condition="x > 0",
                        enabled=True)
        result = server._format_breakpoint(bp)
        self.assertIn("#1", result)
        self.assertIn("main", result)
        self.assertIn("test.c:5", result)
        self.assertIn("x > 0", result)

    def test_format_minimal(self):
        bp = Breakpoint(number=2, type="breakpoint", location="foo")
        result = server._format_breakpoint(bp)
        self.assertIn("#2", result)
        self.assertIn("foo", result)


class FormatFrameTests(unittest.TestCase):
    def test_format_full(self):
        frame = Frame(level=0, address="0x400500", function="main",
                      file="test.c", line=10)
        result = server._format_frame(frame)
        self.assertIn("#0", result)
        self.assertIn("main", result)
        self.assertIn("test.c:10", result)

    def test_format_no_source(self):
        frame = Frame(level=1, address="0x400600")
        result = server._format_frame(frame)
        self.assertIn("#1", result)
        self.assertIn("??", result)


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


class RrRecordToolTests(unittest.TestCase):
    @patch("karellen_rr_mcp.server.rr_record_cmd")
    def test_record_success(self, mock_record):
        mock_record.return_value = ("/traces/test-0", 0, "output", "stderr")
        result = server.rr_record(["./test"])
        self.assertIn("Recording complete", result)
        self.assertIn("/traces/test-0", result)
        self.assertIn("Exit code: 0", result)

    @patch("karellen_rr_mcp.server.rr_record_cmd")
    def test_record_error(self, mock_record):
        mock_record.side_effect = RrError("rr not installed")
        result = server.rr_record(["./test"])
        self.assertIn("Error:", result)
        self.assertIn("rr not installed", result)


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
        self.assertIn("Replay session started", result)
        self.assertIn("12345", result)
        mock_server.start.assert_called_once()
        mock_session.start.assert_called_once()
        mock_session.connect.assert_called_once_with("localhost", 12345)

    def test_replay_start_already_active(self):
        server._gdb_session = MagicMock()
        result = server.rr_replay_start()
        self.assertIn("Error:", result)
        self.assertIn("already active", result)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class RrReplayStopToolTests(unittest.TestCase):
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    def test_stop_no_session(self):
        result = server.rr_replay_stop()
        self.assertIn("No active", result)

    def test_stop_active_session(self):
        server._gdb_session = MagicMock()
        server._replay_server = MagicMock()
        result = server.rr_replay_stop()
        self.assertIn("stopped", result)
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
        self.assertIn("No recordings", result)

    @patch("karellen_rr_mcp.server.rr_list")
    def test_with_recordings(self, mock_list):
        mock_list.return_value = ["/traces/test-0", "/traces/test-1"]
        result = server.rr_list_recordings()
        self.assertIn("/traces/test-0", result)
        self.assertIn("/traces/test-1", result)


class BreakpointToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_set_breakpoint(self):
        self.mock_session.breakpoint_set.return_value = Breakpoint(
            number=1, type="breakpoint", location="main",
            file="test.c", line=5)
        result = server.rr_breakpoint_set("main")
        self.assertIn("#1", result)
        self.assertIn("main", result)

    def test_remove_breakpoint(self):
        result = server.rr_breakpoint_remove(1)
        self.assertIn("removed", result)
        self.mock_session.breakpoint_delete.assert_called_once_with(1)

    def test_list_breakpoints_empty(self):
        self.mock_session.breakpoint_list.return_value = []
        result = server.rr_breakpoint_list()
        self.assertIn("No breakpoints", result)

    def test_list_breakpoints(self):
        self.mock_session.breakpoint_list.return_value = [
            Breakpoint(number=1, type="breakpoint", location="main"),
            Breakpoint(number=2, type="breakpoint", location="foo"),
        ]
        result = server.rr_breakpoint_list()
        self.assertIn("#1", result)
        self.assertIn("#2", result)

    def test_set_watchpoint(self):
        self.mock_session.watchpoint_set.return_value = Breakpoint(
            number=3, type="watchpoint", location="x")
        result = server.rr_watchpoint_set("x")
        self.assertIn("#3", result)

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
        self.assertIn("breakpoint-hit", result)

    def test_continue_reverse(self):
        self.mock_session.continue_execution.return_value = self.stop
        server.rr_continue(reverse=True)
        self.mock_session.continue_execution.assert_called_once_with(reverse=True)

    def test_step(self):
        self.mock_session.step.return_value = self.stop
        result = server.rr_step()
        self.assertIn("breakpoint-hit", result)

    def test_next(self):
        self.mock_session.next.return_value = self.stop
        server.rr_next(count=2)
        self.mock_session.next.assert_called_once_with(count=2, reverse=False)

    def test_finish(self):
        self.mock_session.finish.return_value = self.stop
        result = server.rr_finish()
        self.assertIn("breakpoint-hit", result)

    def test_run_to_event(self):
        self.mock_session.run_to_event.return_value = self.stop
        server.rr_run_to_event(42)
        self.mock_session.run_to_event.assert_called_once_with(42)

    def test_continue_error(self):
        self.mock_session.continue_execution.side_effect = GdbSessionError("failed")
        result = server.rr_continue()
        self.assertIn("Error:", result)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class InspectionToolTests(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        server._gdb_session = self.mock_session

    def test_backtrace(self):
        self.mock_session.backtrace.return_value = [
            Frame(level=0, address="0x500", function="bar", file="b.c", line=3),
            Frame(level=1, address="0x600", function="main", file="a.c", line=10),
        ]
        result = server.rr_backtrace()
        self.assertIn("bar", result)
        self.assertIn("main", result)

    def test_backtrace_empty(self):
        self.mock_session.backtrace.return_value = []
        result = server.rr_backtrace()
        self.assertIn("No stack frames", result)

    def test_evaluate(self):
        self.mock_session.evaluate.return_value = "42"
        result = server.rr_evaluate("x + 1")
        self.assertIn("x + 1", result)
        self.assertIn("42", result)

    def test_locals(self):
        self.mock_session.locals.return_value = [
            Variable(name="x", value="10", type="int"),
            Variable(name="s", value='"hello"', type="char *"),
        ]
        result = server.rr_locals()
        self.assertIn("x = 10", result)
        self.assertIn("(int)", result)
        self.assertIn("s =", result)

    def test_locals_empty(self):
        self.mock_session.locals.return_value = []
        result = server.rr_locals()
        self.assertIn("No local", result)

    def test_read_memory(self):
        self.mock_session.read_memory.return_value = "deadbeef"
        result = server.rr_read_memory("0x1000", count=16)
        self.assertIn("deadbeef", result)
        self.assertIn("0x1000", result)

    def test_registers(self):
        self.mock_session.registers.return_value = {"0": "0x1", "1": "0x2"}
        result = server.rr_registers()
        self.assertIn("0x1", result)
        self.assertIn("0x2", result)

    def test_source_lines(self):
        self.mock_session.source_lines.return_value = "1\tint main() {\n2\t  return 0;\n"
        result = server.rr_source_lines()
        self.assertIn("int main()", result)

    def test_source_lines_empty(self):
        self.mock_session.source_lines.return_value = ""
        result = server.rr_source_lines()
        self.assertIn("No source", result)

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
        self.assertIn("checkpoint 1", result)

    def test_checkpoint_save_empty(self):
        self.mock_session.checkpoint_save.return_value = ""
        result = server.rr_checkpoint_save()
        self.assertIn("Checkpoint saved", result)

    def test_checkpoint_restore_stop_event(self):
        stop = StopEvent(reason="breakpoint-hit",
                         frame=Frame(level=0, address="0x500", function="main"))
        self.mock_session.checkpoint_restore.return_value = stop
        result = server.rr_checkpoint_restore(1)
        self.assertIn("breakpoint-hit", result)

    def test_checkpoint_restore_string(self):
        self.mock_session.checkpoint_restore.return_value = "restored to checkpoint 1"
        result = server.rr_checkpoint_restore(1)
        self.assertIn("restored", result)

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None


class NoSessionToolTests(unittest.TestCase):
    """Verify tools return errors when no session is active."""
    def setUp(self):
        server._gdb_session = None
        server._replay_server = None

    def test_breakpoint_set_no_session(self):
        result = server.rr_breakpoint_set("main")
        self.assertIn("Error:", result)

    def test_continue_no_session(self):
        result = server.rr_continue()
        self.assertIn("Error:", result)

    def test_backtrace_no_session(self):
        result = server.rr_backtrace()
        self.assertIn("Error:", result)

    def test_evaluate_no_session(self):
        result = server.rr_evaluate("x")
        self.assertIn("Error:", result)
