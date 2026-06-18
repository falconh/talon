"""Load the set of installed Talon-marketplace plugins from installed_plugins.json."""
from __future__ import annotations
import json


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
