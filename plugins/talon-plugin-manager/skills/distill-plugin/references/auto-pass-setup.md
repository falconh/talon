# Auto-pass setup & safety model

How the automatic distillation path runs, and how to make it post safely.

## The two paths

| Path | Trigger | Posts to GitHub? |
| --- | --- | --- |
| **Manual** | You invoke the `distill-plugin` skill | Yes — a human is present and confirms |
| **Auto** | `SessionEnd` hook spawns `claude -p` when a plugin's evidence crosses the threshold | **No by default** — drafts + logs only (opt-in to post) |

## What the auto-pass does (every time it fires)

1. `capture.py` (the `SessionEnd` hook) appends evidence and, when `unprocessed >= threshold`, drops a
   `<plugin>.ready` marker and spawns a detached `claude -p` distill pass for that plugin.
2. The child session reads the queue, builds trajectories, reflects (abstraction-first), classifies
   fault, decides, and runs the redaction gate — exactly like the manual path.
3. **By default it does not post.** It runs in dry-run, so `emit.py` logs each issue it *would* file
   to `~/.claude/talon-distill/pending/<plugin>.log` instead of calling `gh`. Review that log and
   post the ones you want (manually, or by re-running the skill), or enable auto-posting (below).

This keeps an outward-facing, public action (filing issues) opt-in, while everything up to the post —
capture, reflection, redaction — is fully automatic.

## Permissions (why it "just works" without prompts)

The spawn passes a **scoped** `--allowedTools` list (`Read`, `Grep`, `Glob`, `Write`,
`Bash(python3:*)`, `Bash(mkdir:*)`, `Bash(cat:*)`). That is enough to run the whole pipeline:
`gh` is invoked *inside* `python3 emit.py` as a subprocess, not as a separate gated tool call, so
there is no need to grant a global `gh` permission. The pass never uses
`--dangerously-skip-permissions`.

You do **not** need to add anything to `settings.json` for the auto-pass. If you prefer to run the
pass yourself on a schedule instead of from the hook, you can allow the same tools in your project
settings:

```jsonc
// .claude/settings.json
{
  "permissions": {
    "allow": ["Bash(python3:*)"]   // emit.py shells out to gh internally
  }
}
```

## Enabling real auto-posting

Set the env var the hook process inherits:

```bash
export TALON_DISTILL_AUTOPOST=1
```

With this set, the spawned pass omits dry-run and `emit.py` files issues for real (still through the
redaction gate — secrets/denylisted terms are quarantined, never posted). Leave it unset to keep the
safe draft-and-review default.

## Redaction denylist (recommended before enabling auto-post)

The shape-based scrubber catches known secret formats (API keys, tokens, emails) but not your
proprietary terms (internal hostnames, customer/org names). Populate the denylist so those are
quarantined too:

```
# ~/.claude/talon-distill/denylist.txt   (one term per line; # comments ok)
acme-internal.example.com
AcmeCorp
prod-cluster-7
```

## Disabling the auto-pass

Remove (or don't install) the plugin's `hooks/hooks.json`, or simply ignore the `.ready` markers and
run the `distill-plugin` skill manually whenever you want.
