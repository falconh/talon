#!/bin/sh
# SessionEnd capture guard.
#
# The distill capture (distill/capture.py) runs on python3, which is NOT present on every
# workstation or agent harness. Calling python3 directly means a missing runtime fails at
# exit-code 127 with no output — and because the hook is async with no LLM in the loop, the
# failure is silent: evidence is never captured and nothing reports it.
#
# This guard turns that silent failure into a breadcrumb the distill-plugin skill can surface.
# POSIX sh only (macOS/Linux). On Windows the hook shell differs and may not run this; there the
# distill-plugin skill's preflight is the safety net instead.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$DIR/capture.py"   # exec preserves the SessionEnd payload on stdin
fi

# python3 missing: record a non-fatal breadcrumb and exit clean (never block session end).
LOG_DIR="${HOME}/.claude/talon-distill"
mkdir -p "$LOG_DIR" 2>/dev/null || exit 0
printf '%s python3 not found on PATH; talon distill SessionEnd capture skipped\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" >> "$LOG_DIR/runtime.log" 2>/dev/null
exit 0
