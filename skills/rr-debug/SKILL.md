---
description: Debug a crash or test failure using rr reverse debugging. Records a command, replays it, and works backwards from the failure to find the root cause.
---

# rr Reverse Debugging Workflow

Use this skill when the user wants to debug a crash, segfault, test failure, or any bug
where the cause isn't obvious from reading the code.

## Prerequisites

- `rr` and `gdb` must be installed and on PATH
- Linux x86-64 only
- `perf_event_paranoid` must be <= 1: `sysctl kernel.perf_event_paranoid`
- The program should be compiled with debug symbols (`-g`, preferably `-O0` or `-Og`)

## Workflow

### 1. Record the Failure

Generate a random trace directory name under the project directory to keep traces local
and avoid cluttering `~/.local/share/rr/`:

```
rr_record(command=["./failing_test"], trace_dir="<project>/rr-trace-<random>")
```

Pass `working_directory` if the command needs to run from a specific directory.
Pass `env` for additional environment variables (e.g., `{"MALLOC_CHECK_": "3"}`).

### 2. Identify the Right Process (Multi-Process Traces)

If the recorded command spawns child processes (test harnesses, build systems, etc.),
the default replay targets the root process, which is usually NOT what you want.

```
rr_ps(trace_dir="<trace>")
```

Look for the actual program binary in the command column. Use exit codes to identify the
crashing process: negative codes indicate signals (-11 = SIGSEGV, -6 = SIGABRT).

### 3. Start Replay

```
rr_replay_start(trace_dir="<trace>", pid=<pid>)
```

Always pass `pid` for multi-process recordings.

### 4. Navigate to the Bug

- **For crashes/signals**: `rr_continue()` stops automatically at the signal
- **For logic bugs**: set breakpoints first with `rr_breakpoint_set()`, then `rr_continue()`
- **For assertion failures**: `rr_breakpoint_set("abort")` or `rr_breakpoint_set("__assert_fail")`, then `rr_continue()`

### 5. Examine State

- `rr_backtrace()` to see the call stack
- `rr_locals()` to see local variables
- `rr_evaluate("expr")` to evaluate expressions
- `rr_select_frame(N)` to inspect caller frames without stepping
- `rr_source_lines()` to see source code at the current position

### 6. Work Backwards to Root Cause

This is the key advantage of rr. From the point where the bug manifests:

- `rr_next(reverse=True)` or `rr_step(reverse=True)` to walk backwards
- If a variable has a wrong value, use `rr_watchpoint_set("var")` then
  `rr_continue(reverse=True)` to find the exact write that corrupted it
- Use `rr_checkpoint_save()` at interesting points and
  `rr_checkpoint_restore(id)` to jump back
- Use `rr_when()` to note event numbers and `rr_run_to_event(N)` to jump

### 7. Check Other Threads

For concurrency bugs:
- `rr_thread_list()` to see all threads
- `rr_thread_select(id)` to switch context
- Examine each thread's state with `rr_backtrace()` and `rr_locals()`

### 8. Clean Up

```
rr_replay_stop()
rr_rm(trace_dir="<trace>")
```

## Key Rules

- **Never modify source to debug.** rr gives full access to program state at every point
  in execution. No debug prints, trace output, or conditional breakpoints in source needed.
- **Work backwards from symptoms.** Go forward to where the bug manifests, then reverse
  to find the cause.
- **Always use project-local trace_dir.** Generate a random directory name and pass it
  as `trace_dir` to `rr_record`. The directory must NOT already exist.
- **Always clean up traces with `rr_rm()`.** Especially important with project-local
  trace directories.
- **Conditional breakpoints narrow the search.** Use
  `rr_breakpoint_set("file.c:100", condition="i == 42")` to stop only when specific
  conditions hold.
