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

from karellen_rr_mcp import response_parser as parser


class ParseFrameTests(unittest.TestCase):
    def test_full_frame(self):
        payload = {
            "level": "0",
            "addr": "0x0040053c",
            "func": "main",
            "file": "test.c",
            "fullname": "/home/user/test.c",
            "line": "10",
            "args": [{"name": "argc", "value": "1"}],
        }
        frame = parser.parse_frame(payload)
        self.assertEqual(frame.level, 0)
        self.assertEqual(frame.address, "0x0040053c")
        self.assertEqual(frame.function, "main")
        self.assertEqual(frame.file, "test.c")
        self.assertEqual(frame.line, 10)
        self.assertEqual(frame.args, [{"name": "argc", "value": "1"}])

    def test_minimal_frame(self):
        payload = {"level": "2", "addr": "0x00400600"}
        frame = parser.parse_frame(payload)
        self.assertEqual(frame.level, 2)
        self.assertEqual(frame.address, "0x00400600")
        self.assertIsNone(frame.function)
        self.assertIsNone(frame.file)
        self.assertIsNone(frame.line)

    def test_frame_with_fullname_fallback(self):
        payload = {"level": "1", "addr": "0x00400500", "fullname": "/abs/path/foo.c"}
        frame = parser.parse_frame(payload)
        self.assertEqual(frame.file, "/abs/path/foo.c")


class ParseBreakpointTests(unittest.TestCase):
    def test_full_breakpoint(self):
        bp_dict = {
            "number": "1",
            "type": "breakpoint",
            "enabled": "y",
            "original-location": "main",
            "func": "main",
            "file": "test.c",
            "fullname": "/home/user/test.c",
            "line": "5",
            "addr": "0x0040053c",
            "times": "3",
            "cond": "x > 0",
        }
        bp = parser.parse_breakpoint(bp_dict)
        self.assertEqual(bp.number, 1)
        self.assertEqual(bp.type, "breakpoint")
        self.assertEqual(bp.location, "main")
        self.assertTrue(bp.enabled)
        self.assertEqual(bp.condition, "x > 0")
        self.assertEqual(bp.hits, 3)
        self.assertEqual(bp.file, "test.c")
        self.assertEqual(bp.line, 5)
        self.assertEqual(bp.address, "0x0040053c")

    def test_disabled_breakpoint(self):
        bp_dict = {
            "number": "2",
            "type": "breakpoint",
            "enabled": "n",
            "func": "foo",
        }
        bp = parser.parse_breakpoint(bp_dict)
        self.assertEqual(bp.number, 2)
        self.assertFalse(bp.enabled)
        self.assertEqual(bp.location, "foo")


class ParseStopEventTests(unittest.TestCase):
    def test_breakpoint_hit(self):
        response = {
            "type": "notify",
            "message": "stopped",
            "payload": {
                "reason": "breakpoint-hit",
                "bkptno": "1",
                "frame": {
                    "level": "0",
                    "addr": "0x0040053c",
                    "func": "main",
                    "file": "test.c",
                    "line": "10",
                },
            },
        }
        stop = parser.parse_stop_event(response)
        self.assertEqual(stop.reason, "breakpoint-hit")
        self.assertEqual(stop.breakpoint_number, 1)
        self.assertIsNotNone(stop.frame)
        self.assertEqual(stop.frame.function, "main")

    def test_signal_received(self):
        response = {
            "type": "notify",
            "message": "stopped",
            "payload": {
                "reason": "signal-received",
                "signal-name": "SIGSEGV",
                "signal-meaning": "Segmentation fault",
                "frame": {"level": "0", "addr": "0x00400500"},
            },
        }
        stop = parser.parse_stop_event(response)
        self.assertEqual(stop.reason, "signal-received")
        self.assertEqual(stop.signal_name, "SIGSEGV")
        self.assertEqual(stop.signal_meaning, "Segmentation fault")
        self.assertIsNone(stop.breakpoint_number)


class ParseBreakpointListTests(unittest.TestCase):
    def test_multiple_breakpoints(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {
                "BreakpointTable": {
                    "body": [
                        {"number": "1", "type": "breakpoint", "enabled": "y",
                         "func": "main", "original-location": "main"},
                        {"number": "2", "type": "breakpoint", "enabled": "n",
                         "func": "foo", "original-location": "foo.c:10"},
                    ]
                }
            },
        }
        bps = parser.parse_breakpoint_list(response)
        self.assertEqual(len(bps), 2)
        self.assertEqual(bps[0].number, 1)
        self.assertEqual(bps[1].number, 2)
        self.assertFalse(bps[1].enabled)

    def test_empty_breakpoint_list(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {"BreakpointTable": {"body": []}},
        }
        bps = parser.parse_breakpoint_list(response)
        self.assertEqual(len(bps), 0)


class ParseLocalsTests(unittest.TestCase):
    def test_multiple_locals(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {
                "locals": [
                    {"name": "x", "value": "42", "type": "int"},
                    {"name": "s", "value": '"hello"', "type": "char *"},
                ]
            },
        }
        variables = parser.parse_locals(response)
        self.assertEqual(len(variables), 2)
        self.assertEqual(variables[0].name, "x")
        self.assertEqual(variables[0].value, "42")
        self.assertEqual(variables[0].type, "int")
        self.assertEqual(variables[1].name, "s")


class ParseBacktraceTests(unittest.TestCase):
    def test_multiple_frames(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {
                "stack": [
                    {"level": "0", "addr": "0x00400500", "func": "bar", "file": "b.c", "line": "3"},
                    {"level": "1", "addr": "0x00400600", "func": "foo", "file": "a.c", "line": "10"},
                    {"level": "2", "addr": "0x00400700", "func": "main", "file": "main.c", "line": "5"},
                ]
            },
        }
        frames = parser.parse_backtrace(response)
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[0].function, "bar")
        self.assertEqual(frames[2].function, "main")


class ParseExpressionValueTests(unittest.TestCase):
    def test_integer_value(self):
        response = {"type": "result", "message": "done", "payload": {"value": "42"}}
        self.assertEqual(parser.parse_expression_value(response), "42")

    def test_string_value(self):
        response = {"type": "result", "message": "done",
                    "payload": {"value": '0x400734 "hello"'}}
        self.assertEqual(parser.parse_expression_value(response), '0x400734 "hello"')


class ParseMemoryBytesTests(unittest.TestCase):
    def test_memory_contents(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {
                "memory": [{"begin": "0x1000", "end": "0x1004", "contents": "deadbeef"}]
            },
        }
        self.assertEqual(parser.parse_memory_bytes(response), "deadbeef")

    def test_empty_memory(self):
        response = {"type": "result", "message": "done", "payload": {"memory": []}}
        self.assertEqual(parser.parse_memory_bytes(response), "")


class ParseRegisterTests(unittest.TestCase):
    def test_register_names(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {"register-names": ["rax", "rbx", "rcx"]},
        }
        names = parser.parse_register_names(response)
        self.assertEqual(names, ["rax", "rbx", "rcx"])

    def test_register_values(self):
        response = {
            "type": "result",
            "message": "done",
            "payload": {
                "register-values": [
                    {"number": "0", "value": "0x1"},
                    {"number": "1", "value": "0x2"},
                ]
            },
        }
        values = parser.parse_register_values(response)
        self.assertEqual(values, {"0": "0x1", "1": "0x2"})


class FindResultResponseTests(unittest.TestCase):
    def test_finds_result(self):
        responses = [
            {"type": "console", "payload": "output"},
            {"type": "result", "message": "done", "payload": {}},
        ]
        result = parser.find_result_response(responses)
        self.assertIsNotNone(result)
        self.assertEqual(result["message"], "done")

    def test_returns_none_when_no_result(self):
        responses = [{"type": "console", "payload": "output"}]
        self.assertIsNone(parser.find_result_response(responses))


class FindStopEventTests(unittest.TestCase):
    def test_finds_stopped(self):
        responses = [
            {"type": "result", "message": "running"},
            {"type": "notify", "message": "stopped", "payload": {"reason": "breakpoint-hit"}},
        ]
        stop = parser.find_stop_event(responses)
        self.assertIsNotNone(stop)

    def test_returns_none_when_no_stop(self):
        responses = [{"type": "result", "message": "done"}]
        self.assertIsNone(parser.find_stop_event(responses))


class GetConsoleOutputTests(unittest.TestCase):
    def test_concatenates_output(self):
        responses = [
            {"type": "console", "payload": "line 1\n"},
            {"type": "result", "message": "done"},
            {"type": "console", "payload": "line 2\n"},
        ]
        self.assertEqual(parser.get_console_output(responses), "line 1\nline 2\n")

    def test_empty_when_no_console(self):
        responses = [{"type": "result", "message": "done"}]
        self.assertEqual(parser.get_console_output(responses), "")


class IsErrorTests(unittest.TestCase):
    def test_error_response(self):
        self.assertTrue(parser.is_error({"message": "error", "payload": {"msg": "bad"}}))

    def test_done_response(self):
        self.assertFalse(parser.is_error({"message": "done", "payload": {}}))

    def test_none_response(self):
        self.assertTrue(parser.is_error(None))


class GetErrorMessageTests(unittest.TestCase):
    def test_error_message(self):
        response = {"message": "error", "payload": {"msg": "No symbol table"}}
        self.assertEqual(parser.get_error_message(response), "No symbol table")

    def test_none_response(self):
        self.assertEqual(parser.get_error_message(None), "No response received")
