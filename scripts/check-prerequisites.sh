#!/bin/bash
# Check that karellen-rr-mcp prerequisites are available.
# Runs once on SessionStart. Reports missing dependencies via JSON output.

WARNINGS=""

check_command() {
  local cmd="$1"
  local install_hint="$2"
  local path
  path=$(command -v "$cmd" 2>/dev/null)
  if [ -z "$path" ]; then
    WARNINGS="${WARNINGS}- ${cmd} is not installed. ${install_hint}"$'\n'
  elif [ ! -x "$path" ]; then
    WARNINGS="${WARNINGS}- ${cmd} found at ${path} but is not executable. Run: chmod +x ${path}"$'\n'
  fi
}

check_command "karellen-rr-mcp" "Run: pip install karellen-rr-mcp"
check_command "rr" "See https://rr-project.org/ for installation."
check_command "gdb" "Install it with your package manager."

[ -z "$WARNINGS" ] && exit 0

jq -n --arg warnings "$WARNINGS" '{
  systemMessage: ("karellen-rr-mcp plugin: missing prerequisites:\n" + $warnings),
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: ("karellen-rr-mcp plugin prerequisites are missing:\n" + $warnings + "The rr debugging tools will not work until these are resolved.")
  }
}'
