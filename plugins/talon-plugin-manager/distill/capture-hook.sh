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
# All distill state lives under one root; TALON_DISTILL_HOME (an absolute path) overrides
# the default so evals and the auto-pass stay off the user's real store. Mirrors paths.py.
LOG_DIR="${TALON_DISTILL_HOME:-${HOME}/.claude/talon-distill}"
mkdir -p "$LOG_DIR" 2>/dev/null || true

if command -v python3 >/dev/null 2>&1; then
    if ( : >>"$LOG_DIR/capture-hook.err" ) 2>/dev/null; then
        exec python3 "$DIR/capture.py" 2>>"$LOG_DIR/capture-hook.err"   # keep stderr when the err file is writable
    fi
    exec python3 "$DIR/capture.py"   # err file unwritable: still run capture, just no err file
fi

# python3 missing: record a non-fatal breadcrumb and exit clean (never block session end).
printf '%s python3 not found on PATH; talon distill SessionEnd capture skipped\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" >> "$LOG_DIR/runtime.log" 2>/dev/null
exit 0
