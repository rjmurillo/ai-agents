#!/usr/bin/env python3
"""Gate: every root host marketplace file points at a real, matching plugin tree.

ADR-115 Decision 11 makes the committed artifact the contract each host reads.
A marketplace file that names a missing directory, a directory without the
manifest that host loads, or a plugin whose ``name`` differs from that manifest
installs nothing, or installs under a name the listing does not advertise.

One table, ``HOST_MARKETPLACES``, lists every root marketplace file and the
manifest its host reads inside each plugin ``source`` directory. A new host adds
one row. For each plugin entry the gate checks:

  * the file parses as a JSON object with a ``plugins`` list;
  * ``source`` is a string that resolves to a directory inside the repository;
  * that directory holds the host's manifest and the manifest parses;
  * the entry ``name`` equals the manifest ``name``.

Manifest locations, read from the tree rather than assumed: the Claude and
Copilot trees both ship ``.claude-plugin/plugin.json``
(``src/claude`` and ``src/copilot-cli``). Grok Build reads the Claude-format
manifest too, so its row names the same path. Codex reads a root
``plugin.json`` (``src/codex``, ADR-115 Decision 7), and
``.agents/plugins/marketplace.json`` wins over ``.claude-plugin/marketplace.json``
when both exist, so that row is the one Codex installs from.

Stricter than ``build/scripts/check_plugin_manifest_parity.py``: that gate
deliberately does not compare ``name``. This one does, because an install by
name from a mismatched listing is a runtime failure, not house taste.

CLI::

    uv run python scripts/validation/check_host_marketplaces.py [repo-root]

Exit codes (ADR-035):
    0 - Success (prints the examined count)
    1 - Violation (bad source, missing manifest, name mismatch, empty listing)
    2 - Config error (invalid root, marketplace file missing or not a JSON
        object with a ``plugins`` list)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# (marketplace file, manifest path relative to each plugin source directory)
HOST_MARKETPLACES: tuple[tuple[str, str], ...] = (
    (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json"),
    (".github/plugin/marketplace.json", ".claude-plugin/plugin.json"),
    (".grok-plugin/marketplace.json", ".claude-plugin/plugin.json"),
    (".agents/plugins/marketplace.json", "plugin.json"),
)

_OK = 0
_VIOLATION = 1
_CONFIG_ERROR = 2


class MarketplaceConfigError(Exception):
    """A marketplace file is missing or not the expected JSON shape."""


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        msg = f"cannot read {path}: {exc}"
        raise MarketplaceConfigError(msg) from exc


def _load_plugins(repo_root: Path, marketplace: str) -> list[object]:
    path = repo_root / marketplace
    if not path.is_file():
        msg = f"marketplace file not found: {marketplace}"
        raise MarketplaceConfigError(msg)
    data = _load_json(path)
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        msg = f"{marketplace} is not a JSON object with a 'plugins' list"
        raise MarketplaceConfigError(msg)
    return plugins


def _resolve_source(repo_root: Path, source: object) -> Path | str:
    """Return the source directory, or a violation message."""
    if not isinstance(source, str) or not source:
        return f"source must be a non-empty string (got {source!r})"
    root = repo_root.resolve()
    resolved = (root / source).resolve()
    if not resolved.is_relative_to(root):
        return f"source {source!r} resolves outside the repository"
    if not resolved.is_dir():
        return f"source {source!r} is not a directory in the repository"
    return resolved


def _manifest_name(source_dir: Path, manifest_rel: str) -> tuple[str | None, str | None]:
    """Return ``(name, violation)`` for the manifest under ``source_dir``."""
    manifest = source_dir / manifest_rel
    if not manifest.is_file():
        return None, f"missing manifest {manifest_rel} under the source directory"
    try:
        data = _load_json(manifest)
    except MarketplaceConfigError as exc:
        return None, f"unreadable manifest: {exc}"
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name:
        return None, f"manifest {manifest_rel} has no string 'name'"
    return name, None


def _check_entry(repo_root: Path, entry: object, manifest_rel: str) -> str | None:
    """Return a violation message for one plugin entry, or None when clean."""
    if not isinstance(entry, dict):
        return "plugin entry is not a JSON object"
    source_dir = _resolve_source(repo_root, entry.get("source"))
    if isinstance(source_dir, str):
        return source_dir
    manifest_name, problem = _manifest_name(source_dir, manifest_rel)
    if problem:
        return problem
    if entry.get("name") != manifest_name:
        return f"entry name {entry.get('name')!r} does not match manifest name {manifest_name!r}"
    return None


def find_violations(repo_root: Path) -> tuple[list[str], int]:
    """Return ``(violations, examined plugin entries)``.

    Raises ``MarketplaceConfigError`` for a missing or malformed marketplace.
    """
    violations: list[str] = []
    examined = 0
    for marketplace, manifest_rel in HOST_MARKETPLACES:
        plugins = _load_plugins(repo_root, marketplace)
        if not plugins:
            violations.append(f"{marketplace}: lists no plugins")
        for index, entry in enumerate(plugins):
            examined += 1
            problem = _check_entry(repo_root, entry, manifest_rel)
            if problem:
                violations.append(f"{marketplace} [plugin {index}]: {problem}")
    return violations, examined


def validate_host_marketplaces(repo_root: Path) -> bool:
    """Return True when every host marketplace is clean.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``. A config error returns False: the gate could not run.
    """
    return main([str(repo_root)]) == _OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return _CONFIG_ERROR
    try:
        violations, examined = find_violations(repo_root)
    except MarketplaceConfigError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return _CONFIG_ERROR
    if violations:
        print(
            f"[FAIL] {len(violations)} host marketplace violation(s) in {examined} "
            f"plugin entries examined across {len(HOST_MARKETPLACES)} files:",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return _VIOLATION
    print(
        f"[PASS] host marketplaces: {examined} plugin entries examined "
        f"across {len(HOST_MARKETPLACES)} files, 0 violations"
    )
    return _OK


if __name__ == "__main__":
    raise SystemExit(main())
