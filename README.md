# 🦅 Talon

**Talon** is a personal plugin marketplace for AI coding agents. It hosts
reusable **skills** and serves them natively to **both [Claude Code](https://code.claude.com/docs)
and [Codex](https://developers.openai.com/codex)** from a single source of truth.

One repo, two marketplaces, the same skills.

## Plugins in this marketplace

| Plugin | What it does | Source |
| --- | --- | --- |
| `hello-world` | Example/template plugin with a friendly greeting skill. | local (`plugins/hello-world`) |
| `terraform-module-steering` | Steering-document generator + spec-driven orchestrator for secure-by-default Terraform/OpenTofu modules (per-service CIS/FSBP research, wrap-upstream, hardcoded security, docs + verification). | remote, pinned `v1.4.0` ([`falconh/terraform-module-steering`](https://github.com/falconh/terraform-module-steering)) |
| `talon-plugin-manager` | Maintainer plugin: onboard and release plugins on this marketplace (dual Claude Code + Codex, naming guidance, version bumping, PR workflow), plus real-time feedback that offers to file a redacted enhancement issue on a plugin's own repo when one of its skills disappoints the user. | local (`plugins/talon-plugin-manager`) |

Plugins can live **in this repo** (local source) or **in their own repo** (remote
git source); both Claude Code and Codex resolve either kind from the catalogs.

### Maintaining this marketplace

Onboarding a new plugin or cutting a release? Use the **`talon-plugin-manager`** plugin's
`onboard-plugin` skill — it gives naming guidance, encodes the dual-manifest requirement, the
bump → tag → pin release flow, and the PR-only rule. Validate any change with
`python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .`

## Install

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add falconh/talon

# Install a plugin from it
/plugin install hello-world@talon
```

Update later with `/plugin marketplace update talon`.

### Codex

```bash
# Add the marketplace
codex plugin marketplace add falconh/talon

# Then browse and enable plugins in the TUI
/plugins
```

Update later with `codex plugin marketplace upgrade talon`.

> You can also grab a single skill directly, without the marketplace:
> ```bash
> codex
> $skill-installer install https://github.com/falconh/talon/tree/main/plugins/hello-world/skills/greet
> ```

## How it works

Both ecosystems support the same `marketplace add owner/repo` flow and load the
same [`SKILL.md`](https://developers.openai.com/codex/skills) files. They differ
only in where each looks for its catalog and plugin manifest:

| | Claude Code | Codex |
| --- | --- | --- |
| Marketplace catalog | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` |
| Plugin manifest | `plugins/<p>/.claude-plugin/plugin.json` | `plugins/<p>/.codex-plugin/plugin.json` |
| Skills (shared) | `plugins/<p>/skills/<s>/SKILL.md` | same file (via `"skills": "./skills/"`) |
| Add command | `/plugin marketplace add falconh/talon` | `codex plugin marketplace add falconh/talon` |
| Install | `/plugin install <p>@talon` | enable in `/plugins` |

The **skill body lives exactly once**. Both marketplaces point at the same
plugin directories, and each `SKILL.md` carries both `name` and `description`
in its frontmatter so it is valid in both tools.

## Repository layout

```
talon/
├── .claude-plugin/marketplace.json     # Claude Code catalog
├── .agents/plugins/marketplace.json    # Codex catalog
├── plugins/
│   └── hello-world/                     # one plugin = one entry in BOTH catalogs
│       ├── .claude-plugin/plugin.json   # Claude Code manifest
│       ├── .codex-plugin/plugin.json    # Codex manifest
│       └── skills/
│           └── greet/SKILL.md           # shared skill (example/template)
├── AGENTS.md                            # repo context for agents
├── README.md
└── LICENSE
```

## Add a new plugin

Each plugin is its own entry in both catalogs. To add one:

1. **Copy the example** as a starting point:
   ```bash
   cp -r plugins/hello-world plugins/<your-plugin>
   ```
2. **Edit the two plugin manifests** in `plugins/<your-plugin>/`:
   - `.claude-plugin/plugin.json` — set `name`, `description`, `version`.
   - `.codex-plugin/plugin.json` — set the same `name`, `description`,
     `version`, and keep `"skills": "./skills/"`.
3. **Write your skill(s)** under `plugins/<your-plugin>/skills/<skill>/SKILL.md`.
   The frontmatter **must** include both `name` and `description`:
   ```markdown
   ---
   name: <skill-name>
   description: One line on exactly when this skill should trigger.
   ---

   Instructions for the agent...
   ```
4. **Register the plugin in both catalogs:**
   - `.claude-plugin/marketplace.json` → add to `plugins[]`:
     ```json
     {
       "name": "<your-plugin>",
       "source": "./plugins/<your-plugin>",
       "description": "...",
       "version": "0.1.0"
     }
     ```
   - `.agents/plugins/marketplace.json` → add to `plugins[]`:
     ```json
     {
       "name": "<your-plugin>",
       "source": { "source": "local", "path": "./plugins/<your-plugin>" },
       "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
       "category": "<category>"
     }
     ```
5. **Commit and push.** Users pick up the change with
   `/plugin marketplace update talon` (Claude Code) or
   `codex plugin marketplace upgrade talon` (Codex).

### Validate before pushing

- Claude Code: `claude plugin validate plugins/<your-plugin>`
- JSON sanity: every `*.json` file must parse.

## License

[MIT](./LICENSE)
