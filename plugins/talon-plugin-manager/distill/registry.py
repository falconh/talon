"""Load the set of installed Talon-marketplace plugins from installed_plugins.json,
and resolve a plugin's <owner>/<repo> from its manifest."""
from __future__ import annotations
import json
import os
import re

_GH_RE = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s]+)")


def resolve_repo(install_path: str) -> str | None:
    """Resolve <owner>/<repo> from the plugin's manifest (repository/homepage)."""
    if not install_path:
        return None
    for fname in (".claude-plugin/plugin.json", "plugin.json"):
        try:
            with open(os.path.join(install_path, fname), encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("repository", "homepage"):
            url = cfg.get(key)
            if isinstance(url, str):
                m = _GH_RE.search(url)
                if m:
                    repo = m.group(2)
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    return f"{m.group(1)}/{repo}"
    return None


def load_talon_registry(path: str) -> dict[str, str]:
    """Return {plugin_name: install_path} for every plugin installed from the
    'talon' marketplace (key '<name>@talon' in installed_plugins.json)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for key, installs in (data.get("plugins") or {}).items():
        name, _, marketplace = key.rpartition("@")
        if marketplace != "talon" or not name:
            continue
        install_path = ""
        if isinstance(installs, list) and installs:
            install_path = installs[-1].get("installPath", "")
        out[name] = install_path
    return out
