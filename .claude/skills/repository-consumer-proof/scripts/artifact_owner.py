#!/usr/bin/env python3
"""Report which layer owns a repo path, per templates/platforms/binplace.yaml.

  artifact_owner.py --repo . <repo-relative-path>

A path is covered by a manifest row when it equals, or sits under, the row's
source (layer "source"), plugin_tree (layer "plugin"), or install_tree
(layer "installed"). Each match names the row class and how the plugin tree
reaches the install tree: "link" (symlink), "copy" (byte copy), or
"render-only" (no install stage or no plugin stage). Each match also lists
"upstream": other rows whose plugin_tree produces the plugin-side copy, so a
linked file resolves to its canonical source row.

Exit codes: 0 covered, 1 no row covers the path, 2 bad arguments or an
unreadable manifest, 3 reserved (this script runs no external command).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MANIFEST = "templates/platforms/binplace.yaml"
LAYERS = (("source", "source"), ("plugin_tree", "plugin"), ("install_tree", "installed"))


def parse_rows(text: str) -> list[dict]:
    """Parse the flat `rows:` list of the manifest (stdlib only, no PyYAML)."""
    rows: list[dict] = []
    in_rows = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_rows:
            in_rows = stripped == "rows:"
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:]
            rows.append({})
        if ":" not in stripped or not rows:
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        value = value.strip("\"'")
        rows[-1][key.strip()] = None if value in ("", "null", "~") else value
    return rows


def _covers(prefix: str | None, path: str) -> bool:
    if not prefix:
        return False
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _relation(row: dict) -> str:
    if not row.get("plugin_tree") or not row.get("install_tree"):
        return "render-only"
    return "link" if row.get("link") == "true" else "copy"


def _plugin_path(row: dict, path: str) -> str | None:
    """Map a path under the install tree to the same path under the plugin tree."""
    plugin, install = row.get("plugin_tree"), row.get("install_tree")
    if plugin and install and _covers(install, path):
        return plugin.rstrip("/") + path[len(install.rstrip("/")) :]
    return plugin if plugin and _covers(plugin, path) and path else None


def _upstream(rows: list[dict], row: dict, path: str) -> list[dict]:
    """Rows whose plugin_tree produces the plugin-side copy of `path` (the true source)."""
    plugin_path = _plugin_path(row, path) or path
    return [
        {
            "class": other.get("class"),
            "source": other.get("source"),
            "plugin_tree": other.get("plugin_tree"),
        }
        for other in rows
        if other is not row and _covers(other.get("plugin_tree"), plugin_path)
    ]


def owners(rows: list[dict], path: str) -> list[dict]:
    found = []
    for row in rows:
        layers = [name for key, name in LAYERS if _covers(row.get(key), path)]
        if layers:
            found.append(
                {
                    "class": row.get("class"),
                    "layers": layers,
                    "relation": _relation(row),
                    "source": row.get("source"),
                    "plugin_tree": row.get("plugin_tree"),
                    "install_tree": row.get("install_tree"),
                    "compile": row.get("compile"),
                    "upstream": _upstream(rows, row, path) if "source" not in layers else [],
                }
            )
    return found


def _normalize(repo: Path, raw: str) -> str | None:
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(repo.resolve())
        except ValueError:
            return None
    norm = candidate.as_posix()
    while norm.startswith("./"):
        norm = norm[2:]
    if norm.startswith("../") or norm in ("", ".."):
        return None
    return norm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".")
    parser.add_argument("path", help="repo-relative path to classify")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 2
    repo = Path(args.repo)
    manifest = repo / MANIFEST
    try:
        rows = parse_rows(manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        print(
            json.dumps({"error": f"cannot read {MANIFEST}: {exc}", "examined": 0}), file=sys.stderr
        )
        return 2
    if not rows:
        print(
            json.dumps({"error": f"no rows parsed from {MANIFEST}", "examined": 0}), file=sys.stderr
        )
        return 2
    path = _normalize(repo, args.path)
    if path is None:
        print(
            json.dumps({"error": f"path outside the repo: {args.path}", "examined": len(rows)}),
            file=sys.stderr,
        )
        return 2
    matches = owners(rows, path)
    print(json.dumps({"path": path, "owner_rows": matches, "examined": len(rows)}, indent=2))
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
