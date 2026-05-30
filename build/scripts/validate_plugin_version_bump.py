#!/usr/bin/env python3
"""Plugin version-bump validator.

Every packaged plugin in this repo is published from a source directory and
carries a ``.claude-plugin/plugin.json`` with a semantic ``version`` string.
Installed plugin caches key off that version: when the version does not change,
existing installs never re-sync, so deletions and edits inside the source dir
silently fail to reach consumers.

PR #1942 is the motivating failure. It deleted the deprecated ``workflow`` skill
from ``.claude/skills/`` but left ``plugin.json`` at ``0.3.0``. Installs kept
shipping the dead ``/workflow`` from the stale ``0.3.0`` cache; the gap was
caught only by hand in PR #2114. This validator turns that manual catch into a
gate.

RULE
----

When any *content* file under a packaged plugin's source directory changes in
the diff, that plugin's ``plugin.json`` ``version`` MUST be strictly greater
than the version at the base ref. A change to ``plugin.json`` alone (a metadata
edit with no other source change) is not required to bump, and a bump with no
other change is always allowed.

Content file = any path under the source dir except the plugin's own
``plugin.json``.

SCOPE
-----

Three packaged plugins (the only dirs with a ``.claude-plugin/plugin.json``):

    .claude/         -> .claude/.claude-plugin/plugin.json        (project-toolkit, Claude)
    src/claude/      -> src/claude/.claude-plugin/plugin.json     (claude-agents)
    src/copilot-cli/ -> src/copilot-cli/.claude-plugin/plugin.json (project-toolkit, Copilot)

``.github/`` and ``src/vs-code-agents/`` carry no plugin.json and are not
marketplace plugins, so they are out of scope: there is no version to bump.
``marketplace.json`` description counts are gated separately by
``build/scripts/validate_marketplace_counts.py``; this validator does not touch
them.

SEMVER
------

Strictly-greater only. The new version must parse and compare greater than the
old version; the magnitude of the bump (patch vs minor vs major) is not
inferred or enforced.

CLI
---

::

    python3 build/scripts/validate_plugin_version_bump.py --base origin/main
    python3 build/scripts/validate_plugin_version_bump.py --files a b c   # bypass git diff (tests)
    python3 build/scripts/validate_plugin_version_bump.py --format json

EXIT CODES (per ADR-035)
------------------------

0 - all touched plugins bumped (or nothing relevant changed)
1 - one or more touched plugins were not version-bumped
2 - configuration error (repo root absent, git unavailable, version unparseable)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --- Plugin model --------------------------------------------------------


@dataclass(frozen=True)
class PluginManifest:
    """One packaged plugin: a source dir and the manifest that versions it."""

    name: str
    source_dir: str  # posix prefix, no trailing slash
    manifest: str  # posix path to plugin.json (lives under source_dir)


# The three packaged plugins. Each manifest path is itself under its source
# dir, so it is excluded from the "content changed" test below.
PLUGINS: tuple[PluginManifest, ...] = (
    PluginManifest(
        name="project-toolkit (claude)",
        source_dir=".claude",
        manifest=".claude/.claude-plugin/plugin.json",
    ),
    PluginManifest(
        name="claude-agents",
        source_dir="src/claude",
        manifest="src/claude/.claude-plugin/plugin.json",
    ),
    PluginManifest(
        name="project-toolkit (copilot)",
        source_dir="src/copilot-cli",
        manifest="src/copilot-cli/.claude-plugin/plugin.json",
    ),
)


@dataclass
class Violation:
    """One plugin whose source changed without a strictly-greater bump."""

    plugin: str
    manifest: str
    old_version: str | None
    new_version: str | None
    reason: str  # "not-bumped" | "not-increased"
    touched: tuple[str, ...]


# --- Path + version helpers ----------------------------------------------


def _normalize_path(path: str) -> str:
    """Normalize a diff path: back-slashes to forward, strip leading ``./``.

    Does NOT strip leading dots in path components: ``.claude/`` and
    ``.github/`` must survive intact (the install-parity validator records
    the same trap).
    """
    s = path.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def _under(source_dir: str, path: str) -> bool:
    """True when ``path`` lives under ``source_dir`` by path components.

    Component-wise comparison so ``.claude`` does not match ``.claude-plugin``.
    """
    sp = source_dir.split("/")
    pp = _normalize_path(path).split("/")
    return pp[: len(sp)] == sp


def parse_version(value: str) -> tuple[int, ...] | None:
    """Parse a semver core into a comparable int tuple, else ``None``.

    Drops any pre-release (``-rc1``) or build (``+meta``) suffix, then splits
    the numeric core on dots. Returns ``None`` when any core component is not
    an integer; the caller treats ``None`` as a configuration error.
    """
    if not value or not value.strip():
        return None
    core = value.strip().split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    out: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        out.append(int(part))
    return tuple(out) if out else None


# --- Core check (pure) ---------------------------------------------------


def evaluate(
    changed_files: Iterable[str],
    version_pairs: dict[str, tuple[str | None, str | None]],
    plugins: Sequence[PluginManifest] = PLUGINS,
) -> tuple[list[Violation], list[str]]:
    """Pure core: decide violations from a changed set and version pairs.

    ``version_pairs`` maps a plugin manifest path to ``(old, new)`` version
    strings. ``old`` is ``None`` when the manifest did not exist at the base
    ref (a brand-new plugin, nothing to compare against). ``new`` is ``None``
    when the manifest is missing or unreadable on disk now.

    Returns ``(violations, config_errors)``. ``config_errors`` is non-empty
    when a version string cannot be parsed; the CLI maps that to exit 2.
    """
    touched = [_normalize_path(p) for p in changed_files]
    violations: list[Violation] = []
    config_errors: list[str] = []

    for plugin in plugins:
        content = tuple(
            sorted(
                p
                for p in touched
                if _under(plugin.source_dir, p) and p != plugin.manifest
            )
        )
        if not content:
            continue

        old, new = version_pairs.get(plugin.manifest, (None, None))

        if new is None:
            config_errors.append(
                f"{plugin.manifest}: version missing or unreadable on disk; "
                f"cannot verify bump for {plugin.name}"
            )
            continue

        new_tuple = parse_version(new)
        if new_tuple is None:
            config_errors.append(
                f"{plugin.manifest}: current version {new!r} is not valid semver"
            )
            continue

        if old is None:
            # Manifest absent at base: a new plugin. Nothing to compare.
            continue

        old_tuple = parse_version(old)
        if old_tuple is None:
            config_errors.append(
                f"{plugin.manifest}: base version {old!r} is not valid semver"
            )
            continue

        if new_tuple == old_tuple:
            violations.append(
                Violation(
                    plugin=plugin.name,
                    manifest=plugin.manifest,
                    old_version=old,
                    new_version=new,
                    reason="not-bumped",
                    touched=content,
                )
            )
        elif new_tuple < old_tuple:
            violations.append(
                Violation(
                    plugin=plugin.name,
                    manifest=plugin.manifest,
                    old_version=old,
                    new_version=new,
                    reason="not-increased",
                    touched=content,
                )
            )

    return violations, config_errors


# --- I/O: git + disk -----------------------------------------------------


def _read_version_text(text: str) -> str | None:
    """Extract ``version`` from a plugin.json text body, or ``None``."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _disk_version(manifest: str, repo_root: Path) -> str | None:
    """Read the current version from the working tree manifest."""
    path = repo_root / manifest
    try:
        return _read_version_text(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _resolve_merge_base(base_ref: str, repo_root: Path) -> str:
    """Return ``git merge-base <base_ref> HEAD``, or ``base_ref`` if it fails.

    Diffing and reading the prior version from the merge-base gives three-dot
    semantics: only changes introduced on this branch count. Without it, a base
    ref that advanced on its own side after the branch point (a sibling PR
    merged to main) leaks its files into ``base..HEAD`` and the gate flags
    plugins this branch never touched.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", base_ref, "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return base_ref
    if proc.returncode != 0:
        return base_ref
    return proc.stdout.strip() or base_ref


def _base_version(base_ref: str, manifest: str, repo_root: Path) -> str | None:
    """Read the manifest version at ``base_ref`` via ``git show``.

    Returns ``None`` when the manifest did not exist at the base (a new
    plugin) or when git cannot produce it. Both cases mean "no prior version
    to compare", which ``evaluate`` treats as a pass.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{base_ref}:{manifest}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return _read_version_text(proc.stdout)


def _version_pairs(
    base_ref: str, repo_root: Path, plugins: Sequence[PluginManifest] = PLUGINS
) -> dict[str, tuple[str | None, str | None]]:
    """Build the ``(old, new)`` version map for every plugin manifest."""
    pairs: dict[str, tuple[str | None, str | None]] = {}
    for plugin in plugins:
        old = _base_version(base_ref, plugin.manifest, repo_root)
        new = _disk_version(plugin.manifest, repo_root)
        pairs[plugin.manifest] = (old, new)
    return pairs


def find_violations(
    changed_files: Iterable[str],
    *,
    base_ref: str,
    repo_root: Path | None = None,
    plugins: Sequence[PluginManifest] = PLUGINS,
    base_already_resolved: bool = False,
) -> tuple[list[Violation], list[str]]:
    """Resolve versions from git/disk, then run the pure ``evaluate`` check.

    ``base_ref`` is collapsed to its merge-base with HEAD so the prior version
    is read from the branch point, matching the three-dot changed-file set the
    CLI computes. When ``base_already_resolved`` is True, the merge-base
    resolution is skipped (caller has already resolved it).
    """
    root = repo_root or _REPO_ROOT
    effective_base = base_ref if base_already_resolved else _resolve_merge_base(base_ref, root)
    pairs = _version_pairs(effective_base, root, plugins)
    return evaluate(changed_files, pairs, plugins)


def _git_diff_files(base: str, repo_root: Path) -> tuple[list[str], int, str]:
    """Return changed paths from ``git diff --name-only base..HEAD``."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", f"{base}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], 2, f"git diff failed: {exc}"
    if proc.returncode != 0:
        return (
            [],
            2,
            f"git diff --name-only {base}..HEAD exit {proc.returncode}: "
            f"{proc.stderr.strip()}",
        )
    return [ln for ln in proc.stdout.splitlines() if ln.strip()], 0, ""


# --- Output --------------------------------------------------------------


def _format_text(violations: Sequence[Violation], config_errors: Sequence[str]) -> str:
    if config_errors and not violations:
        lines = ["plugin-version-bump: CONFIG ERROR"]
        lines.extend(f"  {e}" for e in config_errors)
        return "\n".join(lines)
    if not violations:
        return "plugin-version-bump: OK"
    lines = ["plugin-version-bump: NOT BUMPED"]
    for v in violations:
        lines.append("")
        lines.append(f"  [{v.reason}] {v.plugin}")
        lines.append(f"    manifest: {v.manifest}")
        lines.append(f"    version:  {v.old_version} (base) -> {v.new_version} (now)")
        lines.append("    changed under source dir:")
        for p in v.touched:
            lines.append(f"      {p}")
    lines.append("")
    lines.append(
        "Fix: bump the `version` in each manifest above to a strictly greater "
        "semver. Source changed but the published version did not, so installs "
        "will not re-sync."
    )
    if config_errors:
        lines.append("")
        lines.append("Config errors:")
        lines.extend(f"  {e}" for e in config_errors)
    return "\n".join(lines)


def _format_json(violations: Sequence[Violation], config_errors: Sequence[str]) -> str:
    payload = {
        "bumped": not violations,
        "violations": [
            {
                "plugin": v.plugin,
                "manifest": v.manifest,
                "old_version": v.old_version,
                "new_version": v.new_version,
                "reason": v.reason,
                "touched": list(v.touched),
            }
            for v in violations
        ],
        "config_errors": list(config_errors),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


# --- CLI -----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gate plugin.json version bumps on plugin source changes.",
    )
    p.add_argument(
        "--base",
        default="origin/main",
        help="Git base ref to diff against (default: origin/main).",
    )
    p.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Explicit changed-file list (bypass git diff). Useful for tests.",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repo root (default: derived from script path).",
    )
    p.add_argument("--format", choices=("text", "json"), default="text")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = (args.repo_root or _REPO_ROOT).resolve()
    if not repo_root.is_dir():
        print(f"error: repo root not found: {repo_root}", file=sys.stderr)
        return 2

    if args.files is not None:
        changed = list(args.files)
        base = args.base
    else:
        # Collapse to the merge-base so the diff and the version read both use
        # three-dot semantics (only this branch's changes; ignore work the
        # base ref advanced on its own side).
        base = _resolve_merge_base(args.base, repo_root)
        changed, rc, err = _git_diff_files(base, repo_root)
        if rc != 0:
            print(err, file=sys.stderr)
            return 2

    violations, config_errors = find_violations(
        changed, base_ref=base, repo_root=repo_root,
        base_already_resolved=(args.files is None),
    )

    if args.format == "json":
        print(_format_json(violations, config_errors))
    else:
        print(_format_text(violations, config_errors))

    if violations:
        return 1
    if config_errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
