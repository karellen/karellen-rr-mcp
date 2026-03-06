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

"""GDB/MI session wrapper using pygdbmi GdbController."""

import logging
import os
import time

from pygdbmi.gdbcontroller import GdbController

from karellen_rr_mcp import mi_commands as mi
from karellen_rr_mcp import response_parser as parser

logger = logging.getLogger(__name__)


def _env_timeout(name, default):
    """Read a timeout from environment variable, falling back to default."""
    value = os.environ.get(name)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            logger.warning("Invalid value for %s: %r, using default %d", name, value, default)
    return default


TIMEOUT_CONNECT = _env_timeout("RR_MCP_TIMEOUT_CONNECT", 60)
TIMEOUT_BREAKPOINT = _env_timeout("RR_MCP_TIMEOUT_BREAKPOINT", 30)
TIMEOUT_FORWARD = _env_timeout("RR_MCP_TIMEOUT_FORWARD", 120)
TIMEOUT_REVERSE = _env_timeout("RR_MCP_TIMEOUT_REVERSE", 300)
TIMEOUT_EVAL = _env_timeout("RR_MCP_TIMEOUT_EVAL", 30)


class GdbSessionError(Exception):
    pass


class GdbSession:
    def __init__(self, gdb_controller=None):
        self._controller = gdb_controller
        self._connected = False

    def start(self):
        if self._controller is None:
            self._controller = GdbController(["gdb", "--nx", "--quiet", "--interpreter=mi3"])

    def connect(self, host, port):
        cmd = mi.target_select_remote(host, port)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_CONNECT,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to connect: %s" % parser.get_error_message(result))
        self._connected = True

    def is_connected(self):
        return self._connected

    def breakpoint_set(self, location, condition=None, temporary=False):
        cmd = mi.break_insert(location, condition=condition, temporary=temporary)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_BREAKPOINT,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to set breakpoint: %s" % parser.get_error_message(result))
        payload = result.get("payload", {}) or {}
        bkpt = payload.get("bkpt", {})
        return parser.parse_breakpoint(bkpt)

    def breakpoint_delete(self, breakpoint_number):
        cmd = mi.break_delete(breakpoint_number)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_BREAKPOINT,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to delete breakpoint: %s" % parser.get_error_message(result))

    def breakpoint_list(self):
        cmd = mi.break_list()
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_BREAKPOINT,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to list breakpoints: %s" % parser.get_error_message(result))
        return parser.parse_breakpoint_list(result)

    def watchpoint_set(self, expression, access_type="write"):
        cmd = mi.watch_insert(expression, access_type=access_type)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_BREAKPOINT,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to set watchpoint: %s" % parser.get_error_message(result))
        payload = result.get("payload", {}) or {}
        # watchpoint response uses "wpt", "hw-awpt", or "hw-rwpt"
        for key in ("wpt", "hw-awpt", "hw-rwpt", "bkpt"):
            if key in payload:
                return parser.parse_breakpoint(payload[key])
        return None

    def continue_execution(self, reverse=False):
        if reverse:
            cmd = mi.exec_continue_reverse()
        else:
            cmd = mi.exec_continue()
        timeout = TIMEOUT_REVERSE if reverse else TIMEOUT_FORWARD
        responses = self._write_until(cmd, timeout_sec=timeout,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Continue failed: %s" % parser.get_error_message(result))
        return None

    def step(self, count=1, reverse=False):
        if reverse:
            cmd = mi.exec_step_reverse()
        else:
            cmd = mi.exec_step(count)
        timeout = TIMEOUT_REVERSE if reverse else TIMEOUT_FORWARD
        responses = self._write_until(cmd, timeout_sec=timeout,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Step failed: %s" % parser.get_error_message(result))
        return None

    def next(self, count=1, reverse=False):
        if reverse:
            cmd = mi.exec_next_reverse()
        else:
            cmd = mi.exec_next(count)
        timeout = TIMEOUT_REVERSE if reverse else TIMEOUT_FORWARD
        responses = self._write_until(cmd, timeout_sec=timeout,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Next failed: %s" % parser.get_error_message(result))
        return None

    def finish(self, reverse=False):
        if reverse:
            cmd = mi.exec_finish_reverse()
        else:
            cmd = mi.exec_finish()
        timeout = TIMEOUT_REVERSE if reverse else TIMEOUT_FORWARD
        responses = self._write_until(cmd, timeout_sec=timeout,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Finish failed: %s" % parser.get_error_message(result))
        return None

    def run_to_event(self, event_number):
        cmd = mi.rr_seek(event_number)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_FORWARD,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        return None

    def backtrace(self, max_depth=None):
        cmd = mi.stack_list_frames(max_depth=max_depth)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Backtrace failed: %s" % parser.get_error_message(result))
        return parser.parse_backtrace(result)

    def evaluate(self, expression):
        cmd = mi.data_evaluate_expression(expression)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Evaluate failed: %s" % parser.get_error_message(result))
        return parser.parse_expression_value(result)

    def locals(self):
        cmd = mi.stack_list_locals()
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Locals failed: %s" % parser.get_error_message(result))
        return parser.parse_locals(result)

    def read_memory(self, address, count=64):
        cmd = mi.data_read_memory_bytes(address, count)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Read memory failed: %s" % parser.get_error_message(result))
        return parser.parse_memory_bytes(result)

    def registers(self, register_names=None):
        if register_names:
            # First get register name-to-number mapping
            name_cmd = mi.data_list_register_names()
            name_responses = self._write_until(name_cmd, timeout_sec=TIMEOUT_EVAL,
                                               predicate=lambda r: parser.find_result_response(r) is not None)
            name_result = parser.find_result_response(name_responses)
            if parser.is_error(name_result):
                raise GdbSessionError("Register names failed: %s" % parser.get_error_message(name_result))
            all_names = parser.parse_register_names(name_result)
            reg_numbers = []
            for rn in register_names:
                if rn in all_names:
                    reg_numbers.append(all_names.index(rn))
            cmd = mi.data_list_register_values(register_numbers=reg_numbers)
        else:
            cmd = mi.data_list_register_values()
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Registers failed: %s" % parser.get_error_message(result))
        return parser.parse_register_values(result)

    def source_lines(self, file=None, line=None, count=10):
        cmd = mi.list_source_lines(file=file, line=line, count=count)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        console_output = parser.get_console_output(responses)
        if console_output:
            return console_output
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Source listing failed: %s" % parser.get_error_message(result))
        return ""

    def select_frame(self, frame_level):
        cmd = mi.stack_select_frame(frame_level)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Frame selection failed: %s" % parser.get_error_message(result))

    def thread_info(self, thread_id=None):
        cmd = mi.thread_info(thread_id=thread_id)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Thread info failed: %s" % parser.get_error_message(result))
        return parser.parse_thread_info(result)

    def thread_select(self, thread_id):
        cmd = mi.thread_select(thread_id)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Thread select failed: %s" % parser.get_error_message(result))

    def rr_when(self):
        cmd = mi.rr_when()
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        return parser.get_console_output(responses)

    def checkpoint_save(self):
        cmd = mi.checkpoint_save()
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_EVAL,
                                      predicate=lambda r: parser.find_result_response(r) is not None)
        return parser.get_console_output(responses)

    def checkpoint_restore(self, checkpoint_id):
        cmd = mi.checkpoint_restore(checkpoint_id)
        responses = self._write_until(cmd, timeout_sec=TIMEOUT_FORWARD,
                                      predicate=_has_stop_or_error)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        return parser.get_console_output(responses)

    def close(self):
        if self._controller is not None:
            try:
                self._controller.exit()
            except Exception:
                logger.debug("Error closing GDB controller", exc_info=True)
            self._controller = None
        self._connected = False

    def _write_until(self, cmd, timeout_sec=5, predicate=None):
        """Send a command and keep reading until predicate is satisfied.

        pygdbmi's write() may return before the expected response arrives
        (e.g. GDB loading symbols, or rr replaying to a breakpoint).
        This method continues reading until the predicate returns True
        on the accumulated responses, or the deadline is exceeded.

        Args:
            cmd: GDB/MI command string.
            timeout_sec: Overall deadline in seconds.
            predicate: Callable(responses) -> bool. If None, returns after
                       first batch (legacy behavior).
        """
        logger.debug("GDB/MI command: %s", cmd)
        deadline = time.monotonic() + timeout_sec
        responses = self._controller.write(cmd, timeout_sec=min(timeout_sec, 5))
        logger.debug("GDB/MI responses (initial): %s", responses)
        if predicate is None or predicate(responses):
            return responses
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                more = self._controller.get_gdb_response(
                    timeout_sec=min(remaining, 5), raise_error_on_timeout=False)
            except Exception:
                break
            logger.debug("GDB/MI responses (continued): %s", more)
            responses.extend(more)
            if predicate(responses):
                break
        return responses


def _has_stop_or_error(responses):
    """Check if responses contain a stop event or an error result."""
    if parser.find_stop_event(responses) is not None:
        return True
    result = parser.find_result_response(responses)
    if result is not None and parser.is_error(result):
        return True
    return False
