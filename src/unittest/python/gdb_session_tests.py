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
from unittest.mock import MagicMock

from karellen_rr_mcp.gdb_session import GdbSession, GdbSessionError


class GdbSessionConnectTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_connect_success(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "connected", "payload": {}}
        ]
        self.session.connect("localhost", 1234)
        self.assertTrue(self.session.is_connected())
        self.mock_ctrl.write.assert_called_once()
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertIn("extended-remote localhost:1234", cmd)

    def test_connect_delayed_result(self):
        """Result arrives in a later batch after initial console/notify output."""
        self.mock_ctrl.write.return_value = [
            {"type": "notify", "message": "thread-group-added", "payload": {"id": "i1"}},
            {"type": "console", "message": None, "payload": "Reading symbols...\n"},
        ]
        self.mock_ctrl.get_gdb_response.return_value = [
            {"type": "notify", "message": "stopped", "payload": {}},
            {"type": "result", "message": "connected", "payload": {}},
        ]
        self.session.connect("localhost", 1234)
        self.assertTrue(self.session.is_connected())
        self.mock_ctrl.get_gdb_response.assert_called()

    def test_connect_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "Connection refused"}}
        ]
        with self.assertRaises(GdbSessionError) as ctx:
            self.session.connect("localhost", 9999)
        self.assertIn("Connection refused", str(ctx.exception))
        self.assertFalse(self.session.is_connected())


class GdbSessionBreakpointTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_breakpoint_set(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "bkpt": {"number": "1", "type": "breakpoint", "func": "main",
                         "original-location": "main", "enabled": "y"}
            }}
        ]
        bp = self.session.breakpoint_set("main")
        self.assertEqual(bp.number, 1)
        self.assertEqual(bp.location, "main")

    def test_breakpoint_set_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "Function not found"}}
        ]
        with self.assertRaises(GdbSessionError):
            self.session.breakpoint_set("nonexistent")

    def test_breakpoint_delete(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {}}
        ]
        self.session.breakpoint_delete(1)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertIn("-break-delete 1", cmd)

    def test_breakpoint_list(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "BreakpointTable": {
                    "body": [
                        {"number": "1", "type": "breakpoint", "enabled": "y",
                         "func": "main", "original-location": "main"},
                        {"number": "2", "type": "breakpoint", "enabled": "n",
                         "func": "foo", "original-location": "foo.c:5"},
                    ]
                }
            }}
        ]
        bps = self.session.breakpoint_list()
        self.assertEqual(len(bps), 2)
        self.assertEqual(bps[0].number, 1)
        self.assertEqual(bps[1].number, 2)


class GdbSessionWatchpointTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_watchpoint_set_write(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "wpt": {"number": "3", "type": "watchpoint", "original-location": "x",
                        "enabled": "y"}
            }}
        ]
        bp = self.session.watchpoint_set("x")
        self.assertEqual(bp.number, 3)

    def test_watchpoint_set_access(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "hw-awpt": {"number": "4", "type": "acc watchpoint",
                            "original-location": "y", "enabled": "y"}
            }}
        ]
        bp = self.session.watchpoint_set("y", access_type="access")
        self.assertEqual(bp.number, 4)


class GdbSessionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def _stop_response(self, reason="breakpoint-hit"):
        return [
            {"type": "result", "message": "running", "payload": None},
            {"type": "notify", "message": "stopped", "payload": {
                "reason": reason,
                "frame": {"level": "0", "addr": "0x00400500", "func": "main"},
            }},
        ]

    def test_continue_forward(self):
        self.mock_ctrl.write.return_value = self._stop_response()
        stop = self.session.continue_execution()
        self.assertEqual(stop.reason, "breakpoint-hit")
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "-exec-continue")

    def test_continue_reverse(self):
        self.mock_ctrl.write.return_value = self._stop_response()
        stop = self.session.continue_execution(reverse=True)
        self.assertEqual(stop.reason, "breakpoint-hit")
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "rc")

    def test_step_forward(self):
        self.mock_ctrl.write.return_value = self._stop_response("end-stepping-range")
        stop = self.session.step(count=1)
        self.assertEqual(stop.reason, "end-stepping-range")

    def test_step_reverse(self):
        self.mock_ctrl.write.return_value = self._stop_response("end-stepping-range")
        self.session.step(reverse=True)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "reverse-step")

    def test_next_forward(self):
        self.mock_ctrl.write.return_value = self._stop_response("end-stepping-range")
        self.session.next(count=2)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "-exec-next 2")

    def test_next_reverse(self):
        self.mock_ctrl.write.return_value = self._stop_response("end-stepping-range")
        self.session.next(reverse=True)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "reverse-next")

    def test_finish_forward(self):
        self.mock_ctrl.write.return_value = self._stop_response("function-finished")
        stop = self.session.finish()
        self.assertEqual(stop.reason, "function-finished")

    def test_finish_reverse(self):
        self.mock_ctrl.write.return_value = self._stop_response("function-finished")
        self.session.finish(reverse=True)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "reverse-finish")

    def test_continue_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "not running"}}
        ]
        with self.assertRaises(GdbSessionError):
            self.session.continue_execution()


class GdbSessionInspectionTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_backtrace(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "stack": [
                    {"level": "0", "addr": "0x500", "func": "bar"},
                    {"level": "1", "addr": "0x600", "func": "foo"},
                ]
            }}
        ]
        frames = self.session.backtrace()
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].function, "bar")

    def test_backtrace_with_depth(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "stack": [{"level": "0", "addr": "0x500", "func": "main"}]
            }}
        ]
        self.session.backtrace(max_depth=5)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertIn("-stack-list-frames 0 4", cmd)

    def test_evaluate(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {"value": "42"}}
        ]
        val = self.session.evaluate("x + 1")
        self.assertEqual(val, "42")

    def test_locals(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "locals": [
                    {"name": "x", "value": "10"},
                    {"name": "y", "value": "20"},
                ]
            }}
        ]
        variables = self.session.locals()
        self.assertEqual(len(variables), 2)
        self.assertEqual(variables[0].name, "x")

    def test_read_memory(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "memory": [{"begin": "0x1000", "end": "0x1010", "contents": "cafebabe"}]
            }}
        ]
        mem = self.session.read_memory("0x1000", 16)
        self.assertEqual(mem, "cafebabe")

    def test_registers_all(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "register-values": [
                    {"number": "0", "value": "0x1"},
                    {"number": "1", "value": "0x2"},
                ]
            }}
        ]
        regs = self.session.registers()
        self.assertEqual(regs, {"0": "0x1", "1": "0x2"})

    def test_source_lines_console_output(self):
        self.mock_ctrl.write.return_value = [
            {"type": "console", "payload": "1\tint main() {\n"},
            {"type": "console", "payload": "2\t  return 0;\n"},
            {"type": "result", "message": "done", "payload": {}},
        ]
        src = self.session.source_lines()
        self.assertIn("int main()", src)


class GdbSessionRrTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_rr_when(self):
        self.mock_ctrl.write.return_value = [
            {"type": "console", "payload": "Current event: 42\n"},
            {"type": "result", "message": "done", "payload": {}},
        ]
        output = self.session.rr_when()
        self.assertIn("42", output)

    def test_run_to_event(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "running", "payload": None},
            {"type": "notify", "message": "stopped", "payload": {
                "reason": "breakpoint-hit",
                "frame": {"level": "0", "addr": "0x500", "func": "main"},
            }},
        ]
        stop = self.session.run_to_event(42)
        self.assertIsNotNone(stop)


class GdbSessionCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_checkpoint_save(self):
        self.mock_ctrl.write.return_value = [
            {"type": "console", "payload": "checkpoint 1 at event 42\n"},
            {"type": "result", "message": "done", "payload": {}},
        ]
        output = self.session.checkpoint_save()
        self.assertIn("checkpoint", output)

    def test_checkpoint_restore(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "running", "payload": None},
            {"type": "notify", "message": "stopped", "payload": {
                "reason": "breakpoint-hit",
                "frame": {"level": "0", "addr": "0x500", "func": "main"},
            }},
        ]
        result = self.session.checkpoint_restore(1)
        self.assertIsNotNone(result)


class GdbSessionFrameTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_select_frame(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {}}
        ]
        self.session.select_frame(2)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertIn("-stack-select-frame 2", cmd)

    def test_select_frame_zero(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {}}
        ]
        self.session.select_frame(0)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertIn("-stack-select-frame 0", cmd)

    def test_select_frame_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "No stack"}}
        ]
        with self.assertRaises(GdbSessionError):
            self.session.select_frame(99)


class GdbSessionThreadTests(unittest.TestCase):
    def setUp(self):
        self.mock_ctrl = MagicMock()
        self.session = GdbSession(gdb_controller=self.mock_ctrl)

    def test_thread_info_all(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "threads": [
                    {"id": "1", "target-id": "Thread 1234.1234", "state": "stopped",
                     "frame": {"level": "0", "addr": "0x500", "func": "main"}},
                    {"id": "2", "target-id": "Thread 1234.1235", "state": "stopped",
                     "frame": {"level": "0", "addr": "0x600", "func": "worker"}},
                ],
                "current-thread-id": "1",
            }}
        ]
        threads = self.session.thread_info()
        self.assertEqual(len(threads), 2)
        self.assertEqual(threads[0].id, "1")
        self.assertTrue(threads[0].current)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "-thread-info")

    def test_thread_info_specific(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {
                "threads": [
                    {"id": "2", "target-id": "Thread 1234.1235", "state": "stopped",
                     "frame": {"level": "0", "addr": "0x600", "func": "worker"}},
                ],
            }}
        ]
        threads = self.session.thread_info(thread_id="2")
        self.assertEqual(len(threads), 1)
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "-thread-info 2")

    def test_thread_info_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "No threads"}}
        ]
        with self.assertRaises(GdbSessionError):
            self.session.thread_info()

    def test_thread_select(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "done", "payload": {}}
        ]
        self.session.thread_select("2")
        cmd = self.mock_ctrl.write.call_args[0][0]
        self.assertEqual(cmd, "-thread-select 2")

    def test_thread_select_error(self):
        self.mock_ctrl.write.return_value = [
            {"type": "result", "message": "error", "payload": {"msg": "Invalid thread"}}
        ]
        with self.assertRaises(GdbSessionError):
            self.session.thread_select("99")


class GdbSessionCloseTests(unittest.TestCase):
    def test_close(self):
        mock_ctrl = MagicMock()
        session = GdbSession(gdb_controller=mock_ctrl)
        mock_ctrl.write.return_value = [
            {"type": "result", "message": "connected", "payload": {}}
        ]
        session.connect("localhost", 1234)
        session.close()
        self.assertFalse(session.is_connected())
        mock_ctrl.exit.assert_called_once()

    def test_close_handles_exception(self):
        mock_ctrl = MagicMock()
        mock_ctrl.exit.side_effect = Exception("already dead")
        session = GdbSession(gdb_controller=mock_ctrl)
        session.close()
        self.assertFalse(session.is_connected())
