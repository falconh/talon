# Talon

Talon is a personal **plugin marketplace** that hosts skills for both
**Claude Code** and **Codex**. The same skills are served to both tools from a
single source of truth.

## Repository layout

- `.claude-plugin/marketplace.json` — Claude Code marketplace catalog.
- `.agents/plugins/marketplace.json` — Codex marketplace catalog.
- `plugins/<plugin>/` — one directory per plugin. Each contains:
  - `.claude-plugin/plugin.json` — Claude Code plugin manifest.
  - `.codex-plugin/plugin.json` — Codex plugin manifest.
  - `skills/<skill>/SKILL.md` — the shared skill(s), loaded by both tools.

## Conventions

- Every `SKILL.md` MUST include both `name` and `description` in its
  frontmatter. Codex requires `name`; Claude Code uses `description`. Including
  both keeps a skill valid in both ecosystems.
- A skill body is the single source of truth — never duplicate it. Both
  marketplaces reference the same `skills/` directory.
- When you add a plugin, add a matching entry to **both** catalog files.

See `README.md` for install and authoring instructions.
