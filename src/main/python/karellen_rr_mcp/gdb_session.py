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

from pygdbmi.gdbcontroller import GdbController

from karellen_rr_mcp import mi_commands as mi
from karellen_rr_mcp import response_parser as parser

logger = logging.getLogger(__name__)

TIMEOUT_CONNECT = 10
TIMEOUT_BREAKPOINT = 5
TIMEOUT_FORWARD = 30
TIMEOUT_REVERSE = 60
TIMEOUT_EVAL = 5


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
        responses = self._write(cmd, timeout_sec=TIMEOUT_CONNECT)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to connect: %s" % parser.get_error_message(result))
        self._connected = True

    def is_connected(self):
        return self._connected

    def breakpoint_set(self, location, condition=None, temporary=False):
        cmd = mi.break_insert(location, condition=condition, temporary=temporary)
        responses = self._write(cmd, timeout_sec=TIMEOUT_BREAKPOINT)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to set breakpoint: %s" % parser.get_error_message(result))
        payload = result.get("payload", {}) or {}
        bkpt = payload.get("bkpt", {})
        return parser.parse_breakpoint(bkpt)

    def breakpoint_delete(self, breakpoint_number):
        cmd = mi.break_delete(breakpoint_number)
        responses = self._write(cmd, timeout_sec=TIMEOUT_BREAKPOINT)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to delete breakpoint: %s" % parser.get_error_message(result))

    def breakpoint_list(self):
        cmd = mi.break_list()
        responses = self._write(cmd, timeout_sec=TIMEOUT_BREAKPOINT)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Failed to list breakpoints: %s" % parser.get_error_message(result))
        return parser.parse_breakpoint_list(result)

    def watchpoint_set(self, expression, access_type="write"):
        cmd = mi.watch_insert(expression, access_type=access_type)
        responses = self._write(cmd, timeout_sec=TIMEOUT_BREAKPOINT)
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
        responses = self._write(cmd, timeout_sec=timeout)
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
        responses = self._write(cmd, timeout_sec=timeout)
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
        responses = self._write(cmd, timeout_sec=timeout)
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
        responses = self._write(cmd, timeout_sec=timeout)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Finish failed: %s" % parser.get_error_message(result))
        return None

    def run_to_event(self, event_number):
        cmd = mi.rr_seek(event_number)
        responses = self._write(cmd, timeout_sec=TIMEOUT_FORWARD)
        stop = parser.find_stop_event(responses)
        if stop:
            return parser.parse_stop_event(stop)
        return None

    def backtrace(self, max_depth=None):
        cmd = mi.stack_list_frames(max_depth=max_depth)
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Backtrace failed: %s" % parser.get_error_message(result))
        return parser.parse_backtrace(result)

    def evaluate(self, expression):
        cmd = mi.data_evaluate_expression(expression)
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Evaluate failed: %s" % parser.get_error_message(result))
        return parser.parse_expression_value(result)

    def locals(self):
        cmd = mi.stack_list_locals()
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Locals failed: %s" % parser.get_error_message(result))
        return parser.parse_locals(result)

    def read_memory(self, address, count=64):
        cmd = mi.data_read_memory_bytes(address, count)
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Read memory failed: %s" % parser.get_error_message(result))
        return parser.parse_memory_bytes(result)

    def registers(self, register_names=None):
        if register_names:
            # First get register name-to-number mapping
            name_cmd = mi.data_list_register_names()
            name_responses = self._write(name_cmd, timeout_sec=TIMEOUT_EVAL)
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
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Registers failed: %s" % parser.get_error_message(result))
        return parser.parse_register_values(result)

    def source_lines(self, file=None, line=None, count=10):
        cmd = mi.list_source_lines(file=file, line=line, count=count)
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        console_output = parser.get_console_output(responses)
        if console_output:
            return console_output
        result = parser.find_result_response(responses)
        if parser.is_error(result):
            raise GdbSessionError("Source listing failed: %s" % parser.get_error_message(result))
        return ""

    def rr_when(self):
        cmd = mi.rr_when()
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        return parser.get_console_output(responses)

    def checkpoint_save(self):
        cmd = mi.checkpoint_save()
        responses = self._write(cmd, timeout_sec=TIMEOUT_EVAL)
        return parser.get_console_output(responses)

    def checkpoint_restore(self, checkpoint_id):
        cmd = mi.checkpoint_restore(checkpoint_id)
        responses = self._write(cmd, timeout_sec=TIMEOUT_FORWARD)
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

    def _write(self, cmd, timeout_sec=5):
        logger.debug("GDB/MI command: %s", cmd)
        responses = self._controller.write(cmd, timeout_sec=timeout_sec)
        logger.debug("GDB/MI responses: %s", responses)
        return responses
