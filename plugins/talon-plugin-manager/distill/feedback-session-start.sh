#!/bin/sh
# SessionStart: prime the agent to watch for USER dissatisfaction with Talon skill output.
# Claude Code adds this hook's stdout to the session context.
cat <<'DIRECTIVE'
[talon-skill-feedback] After you use any Talon plugin skill, stay alert to whether the USER seems
dissatisfied with its result: they correct or contradict it, redo the work themselves, express
frustration, or abandon the approach it steered toward. If you observe that, invoke the
talon-plugin-manager skill-feedback skill to offer filing a redacted enhancement issue on the
plugin's repo. Judge the user's reaction, never your own output quality. When unsure, do not
interrupt — a false nudge is worse than a missed one.
DIRECTIVE
