# Marketplace manifest & catalog templates

Copy-paste templates for every file a marketplace plugin touches. Replace `<...>` placeholders with
the confirmed marketplace's values — `<owner>`/`<repo>`, `<marketplace-name>`, `<owner-email>` (e.g.
`falconh`, `talon`, and `wongfalcon@gmail.com` for the reference example; resolve them via
`scripts/resolve_marketplace.py`). Keep the two plugin manifests on the same `version`, and keep both
catalog entries describing the same plugin.

## Contents

- [Catalog file locations](#catalog-file-locations)
- [Plugin manifests](#plugin-manifests)
- [Claude Code catalog entry](#claude-code-catalog-entry)
- [Codex catalog entry](#codex-catalog-entry)
- [SKILL.md frontmatter](#skillmd-frontmatter)
- [Catalog file skeletons](#catalog-file-skeletons)

## Catalog file locations

Both live at the **root of the marketplace repo** (identical relative paths for every dual
marketplace):

- Claude Code: `.claude-plugin/marketplace.json`
- Codex: `.agents/plugins/marketplace.json`

## Plugin manifests

These live in the **plugin** (its own repo for a remote plugin, or the marketplace repo's
`plugins/<name>/` for a local one). Both are required for dual support.

`.claude-plugin/plugin.json`:

```json
{
  "name": "<name>",
  "description": "<one-line description>",
  "version": "<X.Y.Z>",
  "author": { "name": "<owner>" },
  "homepage": "https://github.com/<owner>/<repo>",
  "repository": "https://github.com/<owner>/<repo>",
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
  "author": { "name": "<owner>" },
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

**Local source** (plugin vendored under the marketplace repo's `plugins/<name>/`):

```json
{
  "name": "<name>",
  "source": "./plugins/<name>",
  "description": "<one-line description>",
  "version": "<X.Y.Z>",
  "author": { "name": "<owner>" }
}
```

**Remote source** (plugin in its own repo) — use the `url` source with the explicit **HTTPS** clone
URL, and pin `ref` to the release tag:

```json
{
  "name": "<name>",
  "source": { "source": "url", "url": "https://github.com/<owner>/<repo>.git", "ref": "v<X.Y.Z>" },
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
  "source": { "source": "url", "url": "https://github.com/<owner>/<repo>.git", "ref": "v<X.Y.Z>" },
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
  "name": "<marketplace-name>",
  "owner": { "name": "<owner>", "email": "<owner-email>" },
  "metadata": { "description": "<one-line marketplace description>" },
  "plugins": [ /* entries here */ ]
}
```

`.agents/plugins/marketplace.json`:

```json
{
  "name": "<marketplace-name>",
  "interface": { "displayName": "<Marketplace Display Name>" },
  "plugins": [ /* entries here */ ]
}
```

## Optional: `marketplace.config.json` (pinning this skill to a marketplace)

`scripts/resolve_marketplace.py` auto-detects the marketplace this skill was installed from, so no
config is needed in the common case. But if you **clone this plugin into your own marketplace** and
want the target fixed without relying on auto-detection (e.g. for Codex, which has no
`known_marketplaces.json`, or to pin a non-`master` default branch), drop a
`marketplace.config.json` **next to the skill** (`skills/onboard-plugin/marketplace.config.json`);
the resolver reads it before self-locating:

```json
{
  "repo": "<owner>/<repo>",
  "name": "<marketplace-name>",
  "defaultBranch": "<default-branch>"
}
```

Only `repo` is required; omit `defaultBranch` to have it resolved live. The user can also override
per-run with `resolve_marketplace.py --repo <owner>/<repo>`.
