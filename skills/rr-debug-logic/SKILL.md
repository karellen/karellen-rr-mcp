---
description: Debug a logic bug (wrong output, wrong value, incorrect behavior) using rr. Sets breakpoints at the point where the bug is observable, then reverse-executes to find where the computation went wrong.
argument-hint: [command-to-record]
---

# Debug Logic Bug with rr

Use this skill when a program produces wrong output, returns an incorrect value, or
behaves incorrectly without crashing. Unlike crashes (which have a clear failure point),
logic bugs require you to first identify WHERE the wrong value becomes observable,
then work backwards to find WHERE the computation went wrong.

## Workflow

### 1. Record the Program

```
rr_record(command=$ARGUMENTS, trace_dir="<project>/rr-trace-<random>")
```

The program will run to completion (it doesn't crash). rr captures everything.

### 2. Start Replay

```
rr_ps(trace_dir="<trace>")
rr_replay_start(trace_dir="<trace>", pid=<pid>)
```

### 3. Set Breakpoints at the Observable Bug

You need to stop execution at the point where the wrong behavior is visible.
Strategies:

**If you know the function that returns the wrong value:**
```
rr_breakpoint_set("compute_result")
rr_continue()
```
Step through and find where the return value is wrong.

**If you know the line that produces wrong output:**
```
rr_breakpoint_set("output.cpp:42")
rr_continue()
```

**If you know the condition that should hold but doesn't:**
```
rr_breakpoint_set("process_data", condition="result < 0")
rr_continue()
```

**If the bug is in iteration N of a loop:**
```
rr_breakpoint_set("loop_body.cpp:100", condition="i == 42")
rr_continue()
```

### 4. Confirm the Wrong Value

At the breakpoint, examine the state:

```
rr_locals()
rr_evaluate("result")
rr_evaluate("expected_value")
```

Verify that the value is indeed wrong at this point. Save a checkpoint:

```
rr_checkpoint_save()
```

### 5. Trace the Value Backwards

Now work backwards to find where the wrong value originated.

**For a simple variable:**
```
rr_watchpoint_set("result")
rr_continue(reverse=True)
```
This stops at the exact write that set `result` to its current (wrong) value.

**For a computed value (e.g., `a + b` is wrong):**
Check which input is wrong:
```
rr_evaluate("a")
rr_evaluate("b")
```
Then watchpoint the wrong input:
```
rr_watchpoint_set("a")
rr_continue(reverse=True)
```

**For a value from a function call:**
Step into the function that returned the wrong value:
```
rr_checkpoint_restore(<id>)   # Go back to before the call
rr_step()                      # Step into the function
```
Then trace through its logic.

### 6. Repeat Until Root Cause

Often the wrong value came from another wrong value. Keep tracing backwards:

1. Find the wrong value
2. Watchpoint it, reverse-continue to find who wrote it
3. Check if THAT write used correct inputs
4. If not, watchpoint the incorrect input and reverse again

Save checkpoints at each level so you can navigate the chain:

```
rr_checkpoint_save()   # At each interesting point
```

### 7. Verify the Fix Hypothesis

Once you've found the root cause, verify by checking what the correct computation
should have been:

```
rr_evaluate("correct_expression")
```

Compare with what actually happened. This confirms you've found the right place to fix.

### 8. Clean Up

```
rr_replay_stop()
rr_rm(trace_dir="<trace>")
```

## Tips

- Start from the most specific observation point. "The output is wrong" is too broad;
  "the value of `total` at line 42 is 7 but should be 12" is actionable.
- Use `rr_source_lines()` liberally to see the code context as you navigate.
- For bugs in data structures, use `rr_evaluate()` to inspect structure contents:
  `rr_evaluate("*node")`, `rr_evaluate("vec.size()")`, `rr_evaluate("map[key]")`.
- If the bug involves a long chain of computations, use `rr_when()` and
  `rr_run_to_event()` to jump between key points efficiently.
