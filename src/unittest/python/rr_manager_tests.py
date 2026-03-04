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

from karellen_rr_mcp.rr_manager import (
    check_rr_available, check_perf_event_paranoid, record,
    list_recordings, ReplayServer, RrError,
    _parse_trace_dir, _find_latest_trace,
)


class CheckRrAvailableTests(unittest.TestCase):
    @patch("karellen_rr_mcp.rr_manager.subprocess.run")
    def test_rr_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(check_rr_available())

    @patch("karellen_rr_mcp.rr_manager.subprocess.run")
    def test_rr_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        self.assertFalse(check_rr_available())

    @patch("karellen_rr_mcp.rr_manager.subprocess.run")
    def test_rr_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("rr", 5)
        self.assertFalse(check_rr_available())


class CheckPerfEventParanoidTests(unittest.TestCase):
    @patch("builtins.open", create=True)
    def test_paranoid_ok(self, mock_open):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read.return_value = "1\n"
        self.assertTrue(check_perf_event_paranoid())

    @patch("builtins.open", create=True)
    def test_paranoid_too_high(self, mock_open):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read.return_value = "2\n"
        self.assertFalse(check_perf_event_paranoid())

    @patch("builtins.open", side_effect=IOError("not found"))
    def test_paranoid_file_missing(self, mock_open):
        self.assertFalse(check_perf_event_paranoid())


class ParseTraceDirTests(unittest.TestCase):
    def test_parse_standard_output(self):
        stderr = ('rr: Saving execution to trace directory '
                  '`/home/user/.local/share/rr/test-0`.')
        result = _parse_trace_dir(stderr)
        self.assertEqual(result, "/home/user/.local/share/rr/test-0")

    def test_parse_no_trace_dir(self):
        self.assertIsNone(_parse_trace_dir("some random output"))

    def test_parse_multiline(self):
        stderr = ("rr: some info\n"
                  "rr: Saving execution to trace directory "
                  "`/tmp/rr/prog-1`.\n"
                  "rr: done\n")
        result = _parse_trace_dir(stderr)
        self.assertEqual(result, "/tmp/rr/prog-1")


class FindLatestTraceTests(unittest.TestCase):
    @patch("karellen_rr_mcp.rr_manager.os.path.isdir")
    def test_nonexistent_base_dir(self, mock_isdir):
        mock_isdir.return_value = False
        self.assertIsNone(_find_latest_trace("/nonexistent"))

    @patch("karellen_rr_mcp.rr_manager.os.listdir")
    @patch("karellen_rr_mcp.rr_manager.os.path.getmtime")
    @patch("karellen_rr_mcp.rr_manager.os.path.isdir")
    def test_finds_latest(self, mock_isdir, mock_getmtime, mock_listdir):
        mock_isdir.return_value = True
        mock_listdir.return_value = ["trace-0", "trace-1"]
        mock_getmtime.side_effect = lambda p: 100.0 if "trace-1" in p else 50.0
        result = _find_latest_trace("/base")
        self.assertIn("trace-1", result)


class RecordTests(unittest.TestCase):
    @patch("karellen_rr_mcp.rr_manager.check_rr_available", return_value=False)
    def test_record_rr_not_available(self, mock_check):
        with self.assertRaises(RrError) as ctx:
            record(["./test"])
        self.assertIn("not installed", str(ctx.exception))

    @patch("karellen_rr_mcp.rr_manager._find_latest_trace", return_value="/traces/test-0")
    @patch("karellen_rr_mcp.rr_manager.subprocess.run")
    @patch("karellen_rr_mcp.rr_manager.check_perf_event_paranoid", return_value=True)
    @patch("karellen_rr_mcp.rr_manager.check_rr_available", return_value=True)
    def test_record_success(self, mock_avail, mock_paranoid, mock_run, mock_latest):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr='rr: Saving execution to trace directory `/traces/test-0`.',
        )
        trace_dir, exit_code, stdout, stderr = record(["./test"])
        self.assertEqual(trace_dir, "/traces/test-0")
        self.assertEqual(exit_code, 0)

    @patch("karellen_rr_mcp.rr_manager.check_perf_event_paranoid", return_value=False)
    @patch("karellen_rr_mcp.rr_manager.check_rr_available", return_value=True)
    def test_record_paranoid_too_high(self, mock_avail, mock_paranoid):
        with self.assertRaises(RrError) as ctx:
            record(["./test"])
        self.assertIn("perf_event_paranoid", str(ctx.exception))


class ListRecordingsTests(unittest.TestCase):
    @patch("karellen_rr_mcp.rr_manager.os.path.isdir", return_value=False)
    def test_nonexistent_dir(self, mock_isdir):
        self.assertEqual(list_recordings("/nonexistent"), [])

    @patch("karellen_rr_mcp.rr_manager.os.path.isdir")
    @patch("karellen_rr_mcp.rr_manager.os.listdir")
    def test_lists_directories(self, mock_listdir, mock_isdir):
        mock_isdir.side_effect = lambda p: True
        mock_listdir.return_value = ["trace-0", "trace-1"]
        result = list_recordings("/base")
        self.assertEqual(len(result), 2)
        self.assertIn("/base/trace-0", result)
        self.assertIn("/base/trace-1", result)


class ReplayServerTests(unittest.TestCase):
    def test_initial_state(self):
        server = ReplayServer(trace_dir="/traces/test-0", port=12345)
        self.assertEqual(server.port, 12345)
        self.assertEqual(server.trace_dir, "/traces/test-0")
        self.assertFalse(server.is_running())

    @patch("karellen_rr_mcp.rr_manager.subprocess.Popen")
    @patch("karellen_rr_mcp.rr_manager.time.sleep")
    def test_start_success(self, mock_sleep, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        server = ReplayServer(trace_dir="/traces/test-0", port=12345)
        server.start()
        self.assertTrue(server.is_running())
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        self.assertIn("rr", cmd)
        self.assertIn("replay", cmd)
        self.assertIn("12345", cmd)

    @patch("karellen_rr_mcp.rr_manager.subprocess.Popen")
    @patch("karellen_rr_mcp.rr_manager.time.sleep")
    def test_start_failure(self, mock_sleep, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited immediately
        mock_proc.communicate.return_value = (b"", b"error msg")
        mock_popen.return_value = mock_proc

        server = ReplayServer(trace_dir="/traces/test-0", port=12345)
        with self.assertRaises(RrError):
            server.start()

    def test_stop_when_not_started(self):
        server = ReplayServer(trace_dir="/traces/test-0")
        server.stop()  # Should not raise

    @patch("karellen_rr_mcp.rr_manager.subprocess.Popen")
    @patch("karellen_rr_mcp.rr_manager.time.sleep")
    def test_stop_running(self, mock_sleep, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        server = ReplayServer(trace_dir="/traces/test-0", port=12345)
        server.start()
        server.stop()
        mock_proc.terminate.assert_called_once()
        self.assertFalse(server.is_running())

    @patch("karellen_rr_mcp.rr_manager.subprocess.Popen")
    @patch("karellen_rr_mcp.rr_manager.time.sleep")
    def test_stop_timeout_kills(self, mock_sleep, mock_popen):
        from subprocess import TimeoutExpired
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [TimeoutExpired("rr", 5), None]
        mock_popen.return_value = mock_proc

        server = ReplayServer(trace_dir="/traces/test-0", port=12345)
        server.start()
        server.stop()
        mock_proc.kill.assert_called_once()
