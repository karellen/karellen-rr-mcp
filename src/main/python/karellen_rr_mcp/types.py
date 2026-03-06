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

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Breakpoint:
    number: int
    type: str
    location: str
    enabled: bool = True
    condition: Optional[str] = None
    hits: int = 0
    file: Optional[str] = None
    line: Optional[int] = None
    address: Optional[str] = None


@dataclass
class Frame:
    level: int
    address: str
    function: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    args: Optional[List[dict]] = None


@dataclass
class Variable:
    name: str
    value: str
    type: Optional[str] = None


@dataclass
class StopEvent:
    reason: str
    frame: Optional[Frame] = None
    breakpoint_number: Optional[int] = None
    signal_name: Optional[str] = None
    signal_meaning: Optional[str] = None


@dataclass
class RecordingInfo:
    trace_dir: str
    exit_code: Optional[int] = None
    events: Optional[int] = None
    creation_time: Optional[str] = None


@dataclass
class ProcessInfo:
    pid: int
    ppid: Optional[int] = None
    exit_code: Optional[int] = None
    cmd: Optional[str] = None


@dataclass
class ThreadInfo:
    id: str
    target_id: Optional[str] = None
    name: Optional[str] = None
    state: Optional[str] = None
    frame: Optional[Frame] = None
    current: bool = False
