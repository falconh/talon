# Domain signals (`distill.json`) — shared contract

Single source of truth for the domain-signal map used to detect **under-trigger** — a session
where a plugin's territory was clearly active but the plugin's skill never fired. Both
`onboard-plugin` (which offers to *declare* a map) and `distill-plugin` (which *reads* it, and
*infers* one when absent) rely on this contract. The loader is `distill/detect.py:load_domain_map`.

## Schema

```json
{
  "domain_globs": ["**/*.tf", "**/*.tofu"],
  "domain_cmds":  ["terraform", "tofu", "tflint", "checkov"]
}
```

- **`domain_globs`** — path globs that mark this plugin's files. `**` spans directories, `*` stays
  within a path segment (e.g. `**/*.tf` matches `infra/prod/main.tf` and `main.tf`). Matched against
  files touched via `Edit`/`Write`/`Read`/`NotebookEdit`.
- **`domain_cmds`** — CLI tokens that mark this plugin's territory. Matched as whole words against
  `Bash` commands (e.g. `terraform` matches `terraform plan`).

A session is an **under-trigger** for the plugin when a glob or command matches **and** the plugin's
skill did not fire.

## Two sources, with precedence

1. **Declared** — `distill.json` at the plugin root. Authoritative; **always wins**. The plugin
   author owns it; `onboard-plugin` offers to add it at onboarding.
2. **Inferred (fallback)** — `~/.claude/talon-distill/inferred/<plugin>.json`, written by the
   `distill-plugin` pass when a plugin ships no `distill.json`, so under-trigger still works for
   undeclared plugins. A later declared `distill.json` overrides it.

Same schema for both files.

## Keep signals tight (precision over recall)

Loose signals cause **false** under-trigger findings, which is noise. Prefer a few high-precision
globs/commands exclusive to the plugin's domain.

- ✅ `"domain_globs": ["**/*.tf"]`, `"domain_cmds": ["terraform", "tofu"]` — unmistakably Terraform.
- ❌ `"domain_globs": ["**/*.json", "**/*.md"]`, `"domain_cmds": ["git", "python"]` — generic; fires
  on unrelated work.

## When to skip

A plugin with no obvious file/command surface (a pure advisory skill) doesn't need a map — omit it
rather than inventing weak signals.
