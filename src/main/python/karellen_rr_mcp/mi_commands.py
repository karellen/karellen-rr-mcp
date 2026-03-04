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

"""Pure functions that build GDB/MI command strings."""


def target_select_remote(host, port):
    return "-target-select extended-remote %s:%d" % (host, port)


def break_insert(location, condition=None, temporary=False):
    parts = ["-break-insert"]
    if temporary:
        parts.append("-t")
    if condition:
        parts.append("-c")
        parts.append('"%s"' % condition)
    parts.append(location)
    return " ".join(parts)


def break_delete(breakpoint_number):
    return "-break-delete %d" % breakpoint_number


def break_list():
    return "-break-list"


def watch_insert(expression, access_type="write"):
    if access_type == "read":
        return "-break-watch -r %s" % expression
    elif access_type == "access":
        return "-break-watch -a %s" % expression
    return "-break-watch %s" % expression


def exec_continue():
    return "-exec-continue"


def exec_continue_reverse():
    return "rc"


def exec_step(count=1):
    return "-exec-step %d" % count


def exec_step_reverse():
    return "reverse-step"


def exec_next(count=1):
    return "-exec-next %d" % count


def exec_next_reverse():
    return "reverse-next"


def exec_finish():
    return "-exec-finish"


def exec_finish_reverse():
    return "reverse-finish"


def stack_list_frames(max_depth=None):
    if max_depth is not None:
        return "-stack-list-frames 0 %d" % (max_depth - 1)
    return "-stack-list-frames"


def data_evaluate_expression(expression):
    return '-data-evaluate-expression "%s"' % expression


def stack_list_locals(print_values=1):
    return "-stack-list-locals %d" % print_values


def data_read_memory_bytes(address, count):
    return "-data-read-memory-bytes %s %d" % (address, count)


def data_list_register_names():
    return "-data-list-register-names"


def data_list_register_values(fmt="x", register_numbers=None):
    if register_numbers:
        return "-data-list-register-values %s %s" % (fmt, " ".join(str(r) for r in register_numbers))
    return "-data-list-register-values %s" % fmt


def list_source_lines(file=None, line=None, count=10):
    if file and line:
        return "-data-disassemble -f %s -l %d -n %d -- 5" % (file, line, count)
    return "list"


def interpreter_exec_console(command):
    return '-interpreter-exec console "%s"' % command


def rr_when():
    return '-interpreter-exec console "when"'


def rr_seek(event_number):
    return '-interpreter-exec console "run %d"' % event_number


def checkpoint_save():
    return '-interpreter-exec console "checkpoint"'


def checkpoint_restore(checkpoint_id):
    return '-interpreter-exec console "restart %d"' % checkpoint_id
