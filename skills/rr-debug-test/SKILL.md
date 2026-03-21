---
description: Debug a failing test using rr. Records the test suite, identifies the failing subprocess, and reverse-debugs just that process to find the root cause.
argument-hint: [test-command]
---

# Debug Failing Test with rr

Use this skill when a test fails (crash, assertion, wrong result) and you need to find
the root cause. This is especially useful for test harnesses that spawn subprocesses,
where the failing test runs in a child process.

## Workflow

### 1. Record the Test Suite

Record the entire test command. rr captures all subprocesses automatically:

```
rr_record(command=$ARGUMENTS, trace_dir="<project>/rr-trace-<random>")
```

For build-system test runners:
```
rr_record(command=["make", "test"], trace_dir=...)
rr_record(command=["ctest", "--test-dir", "build"], trace_dir=...)
rr_record(command=["pytest", "tests/"], trace_dir=...)
```

### 2. Find the Failing Process

Test harnesses (CTest, pytest, make, shell scripts) spawn child processes. The root
process is the harness, NOT the test. You must identify the correct subprocess:

```
rr_ps(trace_dir="<trace>")
```

**How to identify the right process:**
- Look at the **command** column for the actual test binary or script
- Check **exit codes**: negative = signal (-11 = SIGSEGV, -6 = SIGABRT), non-zero = failure
- The harness process (shell, python, ctest) is usually PID 1 in the trace — skip it
- If multiple tests failed, start with the first non-zero exit code

### 3. Replay the Failing Process

```
rr_replay_start(trace_dir="<trace>", pid=<failing-pid>)
```

**Always pass `pid`** for test recordings. Without it, rr replays the harness process
which lacks test debug symbols and is not where the bug occurred.

### 4. Navigate to the Failure

- **Crash/signal**: `rr_continue()` — stops at signal automatically
- **Assertion failure**: `rr_breakpoint_set("__assert_fail")` or `rr_breakpoint_set("abort")`,
  then `rr_continue()`
- **Test framework assertion** (gtest, catch2, etc.):
  `rr_breakpoint_set("testing::internal::AssertHelper")` for gtest, or set a breakpoint
  on the test function itself
- **Wrong result**: `rr_breakpoint_set("test_function_name")`, then `rr_continue()` and
  step through the test logic

### 5. Examine and Reverse-Debug

```
rr_backtrace()
rr_locals()
```

Work backwards from the failure:
- `rr_next(reverse=True)` to step backwards
- `rr_watchpoint_set("variable")` + `rr_continue(reverse=True)` to find where a value
  was corrupted
- `rr_select_frame(N)` to inspect caller frames

### 6. Clean Up

```
rr_replay_stop()
rr_rm(trace_dir="<trace>")
```

## Tips

- If the test is flaky (sometimes passes, sometimes fails), record multiple runs.
  rr captures the exact execution, so a failing recording will always reproduce.
- For slow test suites, narrow down to the specific test first:
  `rr_record(command=["./test_binary", "--gtest_filter=TestSuite.FailingTest"])`
- Use `rr_evaluate("expr")` to check test expectations at the point of failure.
