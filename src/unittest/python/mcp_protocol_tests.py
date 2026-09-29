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

"""Tests that drive the server through a real MCP client rather than calling tools directly."""

import asyncio
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

from mcp import Client, StdioServerParameters

from karellen_rr_mcp.types import Frame, ThreadInfo
import karellen_rr_mcp.server as server


class _OverlapTracker:
    """Records the peak number of tracked calls in flight at the same time."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def hold(self, result):
        def side_effect(*args, **kwargs):
            with self._lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.2)
            with self._lock:
                self.active -= 1
            return result
        return side_effect


class ToolListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_tools_listed_over_protocol(self):
        registered = await server.mcp.list_tools()
        async with Client(server.mcp) as client:
            result = await client.list_tools()
        names = {t.name for t in result.tools}
        self.assertEqual(names, {t.name for t in registered})
        self.assertIn("rr_record", names)
        self.assertIn("rr_backtrace", names)
        for tool in result.tools:
            self.assertEqual(tool.input_schema.get("type"), "object", tool.name)


class StdioTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_negotiates_modern_protocol(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from karellen_rr_mcp.server import main; main()"],
            env={"PYTHONPATH": os.pathsep.join(sys.path)},
        )
        async with Client(params) as client:
            self.assertEqual(client.protocol_version, "2026-07-28")
            self.assertEqual(client.server_info.name, "karellen-rr-mcp")
            self.assertIn("rr_replay_start", client.instructions)
            result = await client.list_tools()
        names = {t.name for t in result.tools}
        self.assertIn("rr_record", names)
        self.assertIn("rr_backtrace", names)


class ConcurrentToolCallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tracker = _OverlapTracker()
        self.mock_session = MagicMock()
        self.mock_session.is_connected.return_value = True
        self.mock_session.thread_select.side_effect = self.tracker.hold(None)
        self.mock_session.select_frame.side_effect = self.tracker.hold(None)
        self.mock_session.backtrace.side_effect = self.tracker.hold([
            Frame(level=0, address="0x500", function="foo"),
            Frame(level=1, address="0x600", function="main"),
        ])
        self.mock_session.thread_info.side_effect = self.tracker.hold([
            ThreadInfo(id="1", name="main", state="stopped", current=True),
            ThreadInfo(id="2", name="worker", state="stopped", current=False),
        ])
        server._gdb_session = self.mock_session

    def tearDown(self):
        server._gdb_session = None
        server._replay_server = None

    async def test_session_tools_never_overlap(self):
        async with Client(server.mcp) as client:
            results = await asyncio.gather(
                client.call_tool("rr_thread_select", {"thread_id": "2"}),
                client.call_tool("rr_select_frame", {"frame_level": 3}),
                client.call_tool("rr_backtrace", {}),
                client.call_tool("rr_thread_list", {}),
            )
        for result in results:
            self.assertFalse(result.is_error, result.content)
        self.assertEqual(self.tracker.max_active, 1)
