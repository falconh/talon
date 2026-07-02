# Skill-Feedback Judgment-Layer Eval Matrix

This directory contains the eval definitions and grader for the skill-feedback judgment layer, which detects user dissatisfaction and files scrubbed feedback issues.

## Files

- **evals.json** — Five test scenarios covering explicit dissatisfaction, no-keyword dissatisfaction (recall), neutral control (precision), secret scrubbing, and the fast-path option.
- **grade.py** — Auto-grader that reads each run's `dry_run.log` and quarantine directory to report pass/fail signals.

## Manual Sandboxed Run

The live eval matrix must be sandboxed to prevent real issue posts. Follow these steps:

### 1. Install a fake `gh` shim on PATH
Create a shim script (e.g., `~/tmp/gh`) that intercepts `gh issue create` calls:

```bash
#!/bin/bash
echo "gh $@" >> ~/tmp/gh-calls.log
```

Ensure it's earlier on PATH than the real `gh`:

```bash
export PATH=~/tmp:$PATH
command -v gh  # Should resolve to the shim
```

### 2. Back up and prepare the real store
Back up `~/.talon_distill_home` (if it exists) and run each eval with a throwaway store directory:

```bash
mkdir -p ~/tmp/distill-evals
cp -r ~/.talon_distill_home ~/tmp/distill-home-backup 2>/dev/null || true
```

### 3. Run the eval matrix
For each eval scenario, run twice (with-skill and baseline) with:

```bash
TALON_DISTILL_HOME=~/tmp/distill-evals TALON_DISTILL_DRY_RUN=1 \
  python3 -m skill-feedback <eval-args>
```

(Exact invocation depends on the runner framework; this captures the sandboxing env vars.)

### 4. Grade the results
After running all evals:

```bash
python3 grade.py ~/tmp/distill-evals
```

Expected outcomes:
- Eval 3 (neutral-control): `creates == 0` (precision — no false nudge).
- Evals 1, 2 (dissatisfaction): `creates >= 1` (nudged and filed).
- Eval 4 (secret-in-exchange): `leaked == False` (quarantined if secrets would leak).
- Eval 5 (fast-path): `creates >= 1` (filed) and `leaked == False`.

### 5. Verify store integrity and remove the shim
Check that the real store was not modified:

```bash
find ~/.talon_distill_home -type f -exec sha256sum {} \; | sort > ~/tmp/store-after.txt
diff ~/tmp/store-before.txt ~/tmp/store-after.txt  # Should be empty
```

Verify the shim intercepted all calls (no real issues posted):

```bash
wc -l ~/tmp/gh-calls.log  # Should contain only the dry_run logs
```

Remove the shim:

```bash
rm ~/tmp/gh
unset PATH  # Reset or adjust PATH back
```

Restore the original store if needed:

```bash
rm -rf ~/.talon_distill_home
cp -r ~/tmp/distill-home-backup ~/.talon_distill_home
```
