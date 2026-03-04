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

"""rr record/replay subprocess lifecycle management."""

import logging
import os
import socket
import subprocess
import time

from karellen_rr_mcp.types import ProcessInfo

logger = logging.getLogger(__name__)

DEFAULT_TRACE_BASE_DIR = os.path.expanduser("~/.local/share/rr")


def _env_timeout(name, default):
    """Read a timeout from environment variable, falling back to default."""
    value = os.environ.get(name)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            logger.warning("Invalid value for %s: %r, using default %d", name, value, default)
    return default


TIMEOUT_STARTUP = _env_timeout("RR_MCP_TIMEOUT_STARTUP", 30)


class RrError(Exception):
    pass


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def check_rr_available():
    """Check if rr is installed and available on PATH."""
    try:
        result = subprocess.run(["rr", "--version"], capture_output=True, text=True,
                                timeout=5)
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def check_perf_event_paranoid():
    """Check if perf_event_paranoid is set to allow rr recording."""
    try:
        with open("/proc/sys/kernel/perf_event_paranoid", "r") as f:
            value = int(f.read().strip())
        return value <= 1
    except (IOError, ValueError):
        return False


def record(command, working_directory=None, env=None, trace_dir=None):
    """Record a command with rr. Returns the trace directory path.

    Args:
        command: Command to record (list of strings).
        working_directory: Working directory for the recorded process.
        env: Optional environment variables dict for the recorded process.
        trace_dir: Output trace directory. If omitted, rr uses its default.
    """
    if not check_rr_available():
        raise RrError("rr is not installed or not found on PATH")

    if not check_perf_event_paranoid():
        raise RrError("perf_event_paranoid is too high. "
                      "Run: sudo sysctl kernel.perf_event_paranoid=1")

    rr_cmd = ["rr", "record"]
    if trace_dir:
        rr_cmd.extend(["-o", trace_dir])
    rr_cmd.extend(list(command))
    logger.info("Recording: %s", rr_cmd)

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        rr_cmd,
        cwd=working_directory,
        env=run_env,
        capture_output=True,
        text=True,
    )

    # rr writes the trace dir to stderr
    trace_dir = _parse_trace_dir(result.stderr)
    if trace_dir is None:
        trace_dir = _find_latest_trace()

    return trace_dir, result.returncode, result.stdout, result.stderr


def _parse_trace_dir(stderr_output):
    """Try to extract trace directory path from rr stderr output."""
    for line in stderr_output.splitlines():
        # rr typically outputs lines like: "rr: Saving execution to trace directory `...`."
        if "trace directory" in line.lower() or "saving" in line.lower():
            start = line.find("`")
            end = line.find("`", start + 1) if start >= 0 else -1
            if start >= 0 and end > start:
                return line[start + 1:end]
    return None


def _find_latest_trace(base_dir=None):
    """Find the most recently created trace directory."""
    if base_dir is None:
        base_dir = DEFAULT_TRACE_BASE_DIR
    if not os.path.isdir(base_dir):
        return None
    entries = []
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path):
            entries.append((os.path.getmtime(full_path), full_path))
    if not entries:
        return None
    entries.sort(reverse=True)
    return entries[0][1]


def list_recordings(trace_base_dir=None):
    """List available rr trace recordings."""
    if trace_base_dir is None:
        trace_base_dir = DEFAULT_TRACE_BASE_DIR
    if not os.path.isdir(trace_base_dir):
        return []
    recordings = []
    for entry in sorted(os.listdir(trace_base_dir)):
        full_path = os.path.join(trace_base_dir, entry)
        if os.path.isdir(full_path):
            recordings.append(full_path)
    return recordings


def list_processes(trace_dir):
    """List processes in an rr trace recording.

    Args:
        trace_dir: Path to rr trace directory.

    Returns:
        List of ProcessInfo objects.
    """
    if not check_rr_available():
        raise RrError("rr is not installed or not found on PATH")

    result = subprocess.run(
        ["rr", "ps", trace_dir],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RrError("rr ps failed: %s" % result.stderr.strip())

    return _parse_ps_output(result.stdout)


def _parse_ps_output(stdout):
    """Parse rr ps tab-separated output into ProcessInfo list."""
    processes = []
    for line in stdout.splitlines():
        if not line.strip() or line.startswith("PID"):
            continue
        parts = line.split("\t", 3)
        if len(parts) < 1:
            continue
        pid = int(parts[0])
        ppid = None
        if len(parts) > 1 and parts[1] != "--":
            ppid = int(parts[1])
        exit_code = None
        if len(parts) > 2 and parts[2] != "--":
            exit_code = int(parts[2])
        cmd = parts[3] if len(parts) > 3 else None
        processes.append(ProcessInfo(
            pid=pid, ppid=ppid, exit_code=exit_code, cmd=cmd))
    return processes


class ReplayServer:
    """Manages rr replay gdbserver subprocess."""

    def __init__(self, trace_dir=None, port=None, pid=None):
        self._trace_dir = trace_dir
        self._port = port or _find_free_port()
        self._pid = pid
        self._process = None

    @property
    def port(self):
        return self._port

    @property
    def trace_dir(self):
        return self._trace_dir

    def start(self, startup_timeout=TIMEOUT_STARTUP):
        """Start rr replay gdbserver.

        Args:
            startup_timeout: Maximum seconds to wait for rr to start listening.
        """
        cmd = ["rr", "replay", "-s", str(self._port), "-k"]
        if self._pid is not None:
            cmd.extend(["-p", str(self._pid)])
        if self._trace_dir:
            cmd.append(self._trace_dir)

        logger.info("Starting rr replay server: %s", cmd)
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Wait for rr to start listening on the port
        deadline = time.monotonic() + startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                _, stderr = self._process.communicate()
                raise RrError("rr replay failed to start: %s" % stderr.decode())
            if self._is_port_listening():
                logger.info("rr replay server is listening on port %d", self._port)
                return
            time.sleep(0.5)
        # Timed out — process is running but not listening
        self.stop()
        raise RrError("rr replay server did not start listening on port %d "
                      "within %d seconds" % (self._port, startup_timeout))

    def _is_port_listening(self):
        """Check if the rr gdbserver port is accepting connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("localhost", self._port))
                return True
        except (ConnectionRefusedError, OSError):
            return False

    def stop(self):
        """Stop the replay server."""
        if self._process is not None:
            logger.info("Stopping rr replay server")
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            finally:
                self._process = None

    def is_running(self):
        if self._process is None:
            return False
        return self._process.poll() is None
