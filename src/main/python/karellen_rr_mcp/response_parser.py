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

"""Parse pygdbmi response dicts into domain types."""

from karellen_rr_mcp.types import Breakpoint, Frame, Variable, StopEvent


def parse_frame(payload):
    """Parse a frame dict from GDB/MI into a Frame dataclass."""
    return Frame(
        level=int(payload.get("level", 0)),
        address=payload.get("addr", ""),
        function=payload.get("func"),
        file=payload.get("file") or payload.get("fullname"),
        line=int(payload["line"]) if "line" in payload else None,
        args=payload.get("args"),
    )


def parse_breakpoint(bp_dict):
    """Parse a breakpoint dict from GDB/MI into a Breakpoint dataclass."""
    return Breakpoint(
        number=int(bp_dict.get("number", 0)),
        type=bp_dict.get("type", "breakpoint"),
        location=bp_dict.get("original-location", bp_dict.get("func", "")),
        enabled=bp_dict.get("enabled", "y") == "y",
        condition=bp_dict.get("cond"),
        hits=int(bp_dict.get("times", 0)),
        file=bp_dict.get("file") or bp_dict.get("fullname"),
        line=int(bp_dict["line"]) if "line" in bp_dict else None,
        address=bp_dict.get("addr"),
    )


def parse_stop_event(response):
    """Parse a GDB/MI stopped async record into a StopEvent."""
    payload = response.get("payload", {}) or {}

    frame = None
    if "frame" in payload:
        frame = parse_frame(payload["frame"])

    return StopEvent(
        reason=payload.get("reason", "unknown"),
        frame=frame,
        breakpoint_number=int(payload["bkptno"]) if "bkptno" in payload else None,
        signal_name=payload.get("signal-name"),
        signal_meaning=payload.get("signal-meaning"),
    )


def parse_breakpoint_list(response):
    """Parse -break-list response into list of Breakpoint."""
    payload = response.get("payload", {}) or {}
    bp_table = payload.get("BreakpointTable", {})
    body = bp_table.get("body", [])
    return [parse_breakpoint(bp) for bp in body]


def parse_locals(response):
    """Parse -stack-list-locals response into list of Variable."""
    payload = response.get("payload", {}) or {}
    locals_list = payload.get("locals", [])
    return [
        Variable(
            name=v.get("name", ""),
            value=v.get("value", ""),
            type=v.get("type"),
        )
        for v in locals_list
    ]


def parse_backtrace(response):
    """Parse -stack-list-frames response into list of Frame."""
    payload = response.get("payload", {}) or {}
    stack = payload.get("stack", [])
    return [parse_frame(f) for f in stack]


def parse_expression_value(response):
    """Parse -data-evaluate-expression response."""
    payload = response.get("payload", {}) or {}
    return payload.get("value", "")


def parse_memory_bytes(response):
    """Parse -data-read-memory-bytes response."""
    payload = response.get("payload", {}) or {}
    memory = payload.get("memory", [])
    if memory:
        return memory[0].get("contents", "")
    return ""


def parse_register_names(response):
    """Parse -data-list-register-names response."""
    payload = response.get("payload", {}) or {}
    return payload.get("register-names", [])


def parse_register_values(response):
    """Parse -data-list-register-values response."""
    payload = response.get("payload", {}) or {}
    values = payload.get("register-values", [])
    return {v.get("number", ""): v.get("value", "") for v in values}


def find_result_response(responses):
    """Find the result record from a list of pygdbmi responses."""
    for r in responses:
        if r.get("type") == "result":
            return r
    return None


def find_stop_event(responses):
    """Find an async stopped event from a list of pygdbmi responses."""
    for r in responses:
        if r.get("type") == "notify" and r.get("message") == "stopped":
            return r
    return None


def get_console_output(responses):
    """Extract console output text from responses."""
    parts = []
    for r in responses:
        if r.get("type") == "console":
            payload = r.get("payload", "")
            if payload:
                parts.append(payload)
    return "".join(parts)


def is_error(response):
    """Check if a result response is an error."""
    if response is None:
        return True
    return response.get("message") == "error"


def get_error_message(response):
    """Extract error message from an error response."""
    if response is None:
        return "No response received"
    payload = response.get("payload", {}) or {}
    return payload.get("msg", "Unknown error")
