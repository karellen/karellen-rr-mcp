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

from karellen_rr_mcp import mi_commands as mi


class TargetSelectTests(unittest.TestCase):
    def test_target_select_remote(self):
        self.assertEqual(mi.target_select_remote("localhost", 1234),
                         "-target-select extended-remote localhost:1234")

    def test_target_select_remote_different_port(self):
        self.assertEqual(mi.target_select_remote("127.0.0.1", 5678),
                         "-target-select extended-remote 127.0.0.1:5678")


class BreakInsertTests(unittest.TestCase):
    def test_simple_location(self):
        self.assertEqual(mi.break_insert("main"), "-break-insert main")

    def test_file_line_location(self):
        self.assertEqual(mi.break_insert("foo.c:42"), "-break-insert foo.c:42")

    def test_with_condition(self):
        self.assertEqual(mi.break_insert("main", condition="x > 5"),
                         '-break-insert -c "x > 5" main')

    def test_temporary(self):
        self.assertEqual(mi.break_insert("main", temporary=True),
                         "-break-insert -t main")

    def test_temporary_with_condition(self):
        self.assertEqual(mi.break_insert("main", condition="i == 0", temporary=True),
                         '-break-insert -t -c "i == 0" main')


class BreakDeleteTests(unittest.TestCase):
    def test_delete(self):
        self.assertEqual(mi.break_delete(1), "-break-delete 1")

    def test_delete_different_number(self):
        self.assertEqual(mi.break_delete(42), "-break-delete 42")


class BreakListTests(unittest.TestCase):
    def test_break_list(self):
        self.assertEqual(mi.break_list(), "-break-list")


class WatchInsertTests(unittest.TestCase):
    def test_write_watch(self):
        self.assertEqual(mi.watch_insert("x"), "-break-watch x")

    def test_read_watch(self):
        self.assertEqual(mi.watch_insert("x", access_type="read"), "-break-watch -r x")

    def test_access_watch(self):
        self.assertEqual(mi.watch_insert("x", access_type="access"), "-break-watch -a x")


class ExecContinueTests(unittest.TestCase):
    def test_continue_forward(self):
        self.assertEqual(mi.exec_continue(), "-exec-continue")

    def test_continue_reverse(self):
        self.assertEqual(mi.exec_continue_reverse(), "rc")


class ExecStepTests(unittest.TestCase):
    def test_step_default(self):
        self.assertEqual(mi.exec_step(), "-exec-step 1")

    def test_step_count(self):
        self.assertEqual(mi.exec_step(5), "-exec-step 5")

    def test_step_reverse(self):
        self.assertEqual(mi.exec_step_reverse(), "reverse-step")


class ExecNextTests(unittest.TestCase):
    def test_next_default(self):
        self.assertEqual(mi.exec_next(), "-exec-next 1")

    def test_next_count(self):
        self.assertEqual(mi.exec_next(3), "-exec-next 3")

    def test_next_reverse(self):
        self.assertEqual(mi.exec_next_reverse(), "reverse-next")


class ExecFinishTests(unittest.TestCase):
    def test_finish(self):
        self.assertEqual(mi.exec_finish(), "-exec-finish")

    def test_finish_reverse(self):
        self.assertEqual(mi.exec_finish_reverse(), "reverse-finish")


class StackListFramesTests(unittest.TestCase):
    def test_all_frames(self):
        self.assertEqual(mi.stack_list_frames(), "-stack-list-frames")

    def test_limited_depth(self):
        self.assertEqual(mi.stack_list_frames(max_depth=10), "-stack-list-frames 0 9")

    def test_depth_one(self):
        self.assertEqual(mi.stack_list_frames(max_depth=1), "-stack-list-frames 0 0")


class DataEvaluateExpressionTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(mi.data_evaluate_expression("x"),
                         '-data-evaluate-expression "x"')

    def test_complex_expression(self):
        self.assertEqual(mi.data_evaluate_expression("arr[i] + 1"),
                         '-data-evaluate-expression "arr[i] + 1"')


class StackListLocalsTests(unittest.TestCase):
    def test_default(self):
        self.assertEqual(mi.stack_list_locals(), "-stack-list-locals 1")

    def test_no_values(self):
        self.assertEqual(mi.stack_list_locals(print_values=0), "-stack-list-locals 0")


class DataReadMemoryBytesTests(unittest.TestCase):
    def test_read_memory(self):
        self.assertEqual(mi.data_read_memory_bytes("0x1000", 16),
                         "-data-read-memory-bytes 0x1000 16")

    def test_read_memory_large(self):
        self.assertEqual(mi.data_read_memory_bytes("0xdeadbeef", 256),
                         "-data-read-memory-bytes 0xdeadbeef 256")


class DataListRegisterTests(unittest.TestCase):
    def test_register_names(self):
        self.assertEqual(mi.data_list_register_names(), "-data-list-register-names")

    def test_register_values_all(self):
        self.assertEqual(mi.data_list_register_values(), "-data-list-register-values x")

    def test_register_values_specific(self):
        self.assertEqual(mi.data_list_register_values(register_numbers=[0, 1, 2]),
                         "-data-list-register-values x 0 1 2")

    def test_register_values_decimal(self):
        self.assertEqual(mi.data_list_register_values(fmt="d"),
                         "-data-list-register-values d")


class RrCommandTests(unittest.TestCase):
    def test_rr_when(self):
        self.assertEqual(mi.rr_when(), '-interpreter-exec console "when"')

    def test_rr_seek(self):
        self.assertEqual(mi.rr_seek(42), '-interpreter-exec console "run 42"')

    def test_rr_seek_different_event(self):
        self.assertEqual(mi.rr_seek(1000), '-interpreter-exec console "run 1000"')


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_save(self):
        self.assertEqual(mi.checkpoint_save(), '-interpreter-exec console "checkpoint"')

    def test_checkpoint_restore(self):
        self.assertEqual(mi.checkpoint_restore(1), '-interpreter-exec console "restart 1"')

    def test_checkpoint_restore_different_id(self):
        self.assertEqual(mi.checkpoint_restore(5), '-interpreter-exec console "restart 5"')
