---
description: Debug a data race or concurrency bug using rr. Records the program, then uses deterministic replay with thread inspection and watchpoints to find the exact interleaving that caused the race.
argument-hint: [command-to-record]
---

# Debug Data Race with rr

Use this skill when you suspect a data race, deadlock, or concurrency bug. rr records
the exact thread interleaving that occurred, then replays it deterministically so you
can inspect every thread's state at every point.

## Why rr for Concurrency Bugs

- Races are non-deterministic — they may not reproduce on re-run. rr captures the
  exact interleaving and replays it identically every time.
- You can inspect all threads at any point in the execution.
- Watchpoints + reverse execution let you trace a corrupted value back to the
  exact write from the racing thread.

## Workflow

### 1. Record the Failure

Run the program under rr. If the race is intermittent, you may need multiple attempts:

```
rr_record(command=$ARGUMENTS, trace_dir="<project>/rr-trace-<random>")
```

For sanitizer-detected races, enable ThreadSanitizer to make the race more visible:
```
rr_record(command=["./program"], env={"TSAN_OPTIONS": "halt_on_error=1"}, trace_dir=...)
```

### 2. Start Replay

```
rr_ps(trace_dir="<trace>")
rr_replay_start(trace_dir="<trace>", pid=<pid>)
```

### 3. Survey the Threads

Before diving in, understand the thread landscape:

```
rr_continue()
```

At the crash or end point:

```
rr_thread_list()
```

Note which threads exist and their states. Switch between threads to see what each
was doing:

```
rr_thread_select(<tid>)
rr_backtrace()
rr_locals()
```

### 4. Find the Contested Data

Identify the shared variable or memory that is being raced on. This might be obvious
from the crash (e.g., corrupted pointer) or from sanitizer output.

Set a **watchpoint** on the contested data:

```
rr_watchpoint_set("shared_variable")
```

Or on a memory address:

```
rr_watchpoint_set("*(int*)0x7fff5678")
```

### 5. Trace All Accesses

Use continue (forward and reverse) to find every access to the contested data:

```
rr_continue()          # Find the next write
rr_backtrace()         # Who wrote it?
rr_thread_list()       # Which thread?
```

Save checkpoints at each access point:

```
rr_checkpoint_save()   # Save before moving on
rr_continue()          # Next access
```

### 6. Find the Missing Synchronization

Once you have the sequence of accesses across threads, identify where synchronization
is missing:

- Two threads writing without a lock
- Read-after-write without a memory barrier
- Lock ordering violation causing deadlock

Use `rr_continue(reverse=True)` with the watchpoint to walk backwards through all
writes and find the first unsynchronized access.

### 7. Verify the Race Window

Use `rr_when()` to note event numbers at key points:
- Thread A's last synchronized access
- Thread B's unsynchronized access
- The point where corruption becomes visible

```
rr_when()              # Note event number
rr_run_to_event(N)     # Jump to a specific point
```

### 8. Clean Up

```
rr_replay_stop()
rr_rm(trace_dir="<trace>")
```

## Tips

- For deadlocks: the program will hang during recording. Use Ctrl+C or a timeout to
  stop it, then inspect thread states in replay — all threads will be at their
  blocking points.
- rr serializes thread execution (one thread runs at a time), so the race manifests
  as a specific interleaving, not truly parallel execution. This makes it easier to
  reason about.
- Use `rr_evaluate("pthread_mutex_trylock(&mutex)")` to check lock states at any point.
