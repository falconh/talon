# Naming a plugin

Read this when onboarding a plugin that doesn't have a settled `name` yet (Flow A). Releases and
re-pins never rename, so they don't need it — the name is already fixed.

A plugin's name is its **identity, not its address**. It becomes a stable identifier — Codex's plugin
id and Claude Code's skill namespace (`/<plugin>:<skill>`) — and the same plugin may be listed in more
than one marketplace or used on its own. So name it for what it *does*, never for where it's hosted.
Don't prefix it with a marketplace name (`talon-…`): that couples an independent artifact to one home
and adds dead weight to every invocation.

Aim for **concise but self-explanatory** — someone seeing only the name should be able to guess the
plugin's purpose. Work through these questions:

1. **What is the plugin's one job?** Name it after that capability or domain
   (`terraform-module-steering`, `aws-cost-report`, `datadog-monitors`), not a vague umbrella
   (`devtools`, `helpers`).
2. **Could a stranger guess what it does from the name alone?** If not, make it more descriptive. If
   it's a mouthful, cut filler — drop `-plugin`, `-tool`, `-skill`, and marketplace prefixes; they
   carry no information.
3. **Is it specific enough not to collide?** The name sits in a shared namespace next to other
   plugins. Prefer `stripe-webhooks` over `payments`, `pg-migrations` over `db`.
4. **Will it still fit if the plugin grows?** Name the *domain* so adding a second skill doesn't
   outdate it; reserve action words for the skills inside.
5. **Does `/<plugin>:<skill>` read naturally?** Say it aloud. Stutter like `/terraform:terraform-plan`
   means the plugin name is doing the skill's job (or vice versa) — rebalance.
6. **Keep the repo name the same as the plugin `name`** by default. The repo is just the plugin's
   home; matching names make it easy to find and reference.

Hard requirements the tooling needs (not style): **lowercase kebab-case**, **stable** over time
(renaming breaks installs and invocations), and the **same `name`** in both plugin manifests and both
catalog entries.

**Grouping without coupling.** To see all your marketplace plugins at a glance, add a GitHub **topic**
(e.g. `talon`) to each plugin repo, or keep them in a GitHub **org** — metadata that groups repos
without baking the marketplace into the plugin's identity.

**Skill names** (inside a plugin): short, action-oriented kebab-case (`onboard-plugin`,
`create-monitor`) describing what the skill *does*, distinct from the plugin's domain name.

Examples:
- ✅ `terraform-module-steering` — domain + purpose; reads as `/terraform-module-steering:<skill>`
- ✅ `aws-cost-report`, `datadog-monitors`, `stripe-webhooks`
- ⚠️ `talon-terraform` — couples to the marketplace; drop the prefix
- ⚠️ `tf`, `utils` — too terse/generic to convey purpose or avoid collisions
- ⚠️ `terraform-module-steering-plugin` — `-plugin` is filler
