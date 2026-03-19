#!/bin/bash
# Detect crash signals in Bash tool output and suggest rr debugging.
# Runs on PostToolUse and PostToolUseFailure for Bash commands.
# Reads the hook input JSON from stdin.

# Bail early if not on Linux x86-64, dependencies missing, or karellen-rr-mcp not installed
[ "$(uname -s)" = "Linux" ] && [ "$(uname -m)" = "x86_64" ] || exit 0
command -v jq &>/dev/null || exit 0
command -v rr &>/dev/null || exit 0
command -v karellen-rr-mcp &>/dev/null || exit 0

INPUT=$(cat)

SIGNAL_DETECTED=""

# Check 1: Exit code encodes signal (128 + signum)
# tool_response for Bash is text, but we can also check for exit code patterns in it
# PostToolUseFailure has "error" field with exit code info
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null)

if [ "$EVENT" = "PostToolUseFailure" ]; then
  ERROR=$(echo "$INPUT" | jq -r '.error // empty' 2>/dev/null)
  # Extract exit code from error message like "exit code 139" or "status code 139"
  EXIT_CODE=$(echo "$ERROR" | grep -oE '(exit|status) *(code *)?[0-9]+' | grep -oE '[0-9]+' | tail -1)
  if [ -n "$EXIT_CODE" ] && [ "$EXIT_CODE" -ge 129 ] && [ "$EXIT_CODE" -le 159 ]; then
    SIGNUM=$((EXIT_CODE - 128))
    case $SIGNUM in
      4)  SIGNAL_DETECTED="SIGILL (illegal instruction)" ;;
      6)  SIGNAL_DETECTED="SIGABRT (abort)" ;;
      7)  SIGNAL_DETECTED="SIGBUS (bus error)" ;;
      8)  SIGNAL_DETECTED="SIGFPE (floating point exception)" ;;
      11) SIGNAL_DETECTED="SIGSEGV (segmentation fault)" ;;
      *)  SIGNAL_DETECTED="signal $SIGNUM" ;;
    esac
  fi
fi

# Check 2: Text patterns in tool_response (PostToolUse) or error (PostToolUseFailure)
if [ -z "$SIGNAL_DETECTED" ]; then
  TEXT=""
  if [ "$EVENT" = "PostToolUse" ]; then
    TEXT=$(echo "$INPUT" | jq -r '.tool_response // empty' 2>/dev/null)
  elif [ "$EVENT" = "PostToolUseFailure" ]; then
    TEXT=$(echo "$INPUT" | jq -r '.error // empty' 2>/dev/null)
  fi

  if [ -n "$TEXT" ]; then
    # Check for crash/sanitizer signatures in output
    MATCH=$(echo "$TEXT" | grep -oiE \
      'Segmentation fault|SIGSEGV|SIGABRT|SIGBUS|SIGFPE|SIGILL|core dumped|Aborted|Bus error|Illegal instruction|Floating point exception|AddressSanitizer|LeakSanitizer|MemorySanitizer|ThreadSanitizer|UndefinedBehaviorSanitizer' \
      2>/dev/null | head -1)
    if [ -n "$MATCH" ]; then
      SIGNAL_DETECTED="$MATCH"
    fi
  fi
fi

# No crash detected
[ -n "$SIGNAL_DETECTED" ] || exit 0

# Emit suggestion
jq -n --arg sig "$SIGNAL_DETECTED" --arg event "$EVENT" '{
  hookSpecificOutput: {
    hookEventName: $event,
    additionalContext: ("Crash detected: " + $sig + ". This is a good candidate for rr reverse debugging. Use the rr-investigator agent or /karellen-rr-mcp:rr-debug to record and replay this failure with deterministic reverse execution to find the exact root cause without modifying source code.")
  }
}'
