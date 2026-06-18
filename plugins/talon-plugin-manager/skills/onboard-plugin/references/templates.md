# Talon manifest & catalog templates

Copy-paste templates for every file a Talon plugin touches. Replace `<...>` placeholders. Keep the
two plugin manifests on the same `version`, and keep both catalog entries describing the same plugin.

## Contents

- [Catalog file locations](#catalog-file-locations)
- [Plugin manifests](#plugin-manifests)
- [Claude Code catalog entry](#claude-code-catalog-entry)
- [Codex catalog entry](#codex-catalog-entry)
- [SKILL.md frontmatter](#skillmd-frontmatter)
- [Catalog file skeletons](#catalog-file-skeletons)

## Catalog file locations

Both live at the **root of the talon repo**:

- Claude Code: `.claude-plugin/marketplace.json`
- Codex: `.agents/plugins/marketplace.json`

## Plugin manifests

These live in the **plugin** (its own repo for a remote plugin, or `talon/plugins/<name>/` for a
local one). Both are required for dual support.

`.claude-plugin/plugin.json`:

```json
{
  "name": "<name>",
  "description": "<one-line description>",
  "version": "<X.Y.Z>",
  "author": { "name": "falconh" },
  "homepage": "https://github.com/falconh/<repo>",
  "repository": "https://github.com/falconh/<repo>",
  "license": "MIT",
  "keywords": ["<kw>", "<kw>"],
  "skills": "./skills"
}
```

`.codex-plugin/plugin.json` (mirror of the above + a Codex `interface` block):

```json
{
  "name": "<name>",
  "version": "<X.Y.Z>",
  "description": "<one-line description>",
  "author": { "name": "falconh" },
  "license": "MIT",
  "keywords": ["<kw>", "<kw>"],
  "skills": "./skills/",
  "interface": {
    "displayName": "<Human Readable Name>",
    "shortDescription": "<short blurb>",
    "category": "<Development | Productivity | ...>"
  }
}
```

Only `.codex-plugin/plugin.json` lives inside `.codex-plugin/`; everything else (`skills/`, etc.)
stays at the plugin root — same rule as `.claude-plugin/`.

## Claude Code catalog entry

Add to the `plugins` array of `.claude-plugin/marketplace.json`.

**Local source** (plugin vendored under `talon/plugins/<name>/`):

```json
{
  "name": "<name>",
  "source": "./plugins/<name>",
  "description": "<one-line description>",
  "version": "<X.Y.Z>",
  "author": { "name": "falconh" }
}
```

**Remote source** (plugin in its own repo) — use the `url` source with the explicit **HTTPS** clone
URL, and pin `ref` to the release tag:

```json
{
  "name": "<name>",
  "source": { "source": "url", "url": "https://github.com/falconh/<repo>.git", "ref": "v<X.Y.Z>" },
  "description": "<one-line description>",
  "version": "<X.Y.Z>"
}
```

> **Use `url` + HTTPS, not the `github` shorthand, for public plugins.** The
> `{ "source": "github", "repo": "owner/repo" }` form makes Claude Code clone the plugin over **SSH**
> (`git@github.com:…`) when installing, with no HTTPS fallback — so it fails with
> `Permission denied (publickey)` for anyone who hasn't configured a GitHub SSH key (which most
> users installing a public plugin haven't). The explicit `https://…​.git` URL clones over HTTPS and
> needs no credentials for a public repo. This mirrors the Codex `url` entry below, so both catalogs
> resolve the same way.

## Codex catalog entry

Add to the `plugins` array of `.agents/plugins/marketplace.json`.

**Local source:**

```json
{
  "name": "<name>",
  "source": { "source": "local", "path": "./plugins/<name>" },
  "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
  "category": "<Development | Productivity | ...>"
}
```

**Remote source** — pin `ref` to the release tag:

```json
{
  "name": "<name>",
  "source": { "source": "url", "url": "https://github.com/falconh/<repo>.git", "ref": "v<X.Y.Z>" },
  "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
  "category": "<Development | Productivity | ...>"
}
```

Notes:
- The Codex catalog entry has **no** `version` field — Codex reads the version from the plugin's own
  `.codex-plugin/plugin.json`. The `ref` pin is what selects the release.
- `policy.installation`: `AVAILABLE` (user opts in), `INSTALLED_BY_DEFAULT`, or `NOT_AVAILABLE`.

## SKILL.md frontmatter

Every skill, in every plugin, must carry **both** fields:

```markdown
---
name: <skill-name>
description: One line stating exactly when this skill should and should not trigger.
---

Instructions for the agent...
```

`name` is mandatory for Codex discovery; `description` is what both tools match on. Omitting `name`
makes the skill load in Claude Code but stay invisible to Codex.

## Catalog file skeletons

For reference, the shape of each catalog (entries trimmed):

`.claude-plugin/marketplace.json`:

```json
{
  "name": "talon",
  "owner": { "name": "falconh", "email": "wongfalcon@gmail.com" },
  "metadata": { "description": "Talon — a personal marketplace of Claude Code & Codex skills." },
  "plugins": [ /* entries here */ ]
}
```

`.agents/plugins/marketplace.json`:

```json
{
  "name": "talon",
  "interface": { "displayName": "Talon" },
  "plugins": [ /* entries here */ ]
}
```
