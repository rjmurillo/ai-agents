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

Versions MUST be valid SemVer 2.0.0 cores: exactly three dot-separated numeric
identifiers (``MAJOR.MINOR.PATCH``), with an optional ``-prerelease`` and
optional ``+build`` suffix. ``1``, ``1.2``, and ``1.2.3.4`` are rejected as
config errors. Precedence follows the SemVer spec
(https://semver.org/#spec-item-11): a pre-release version has lower precedence
than the associated release, so ``0.3.0-rc1 < 0.3.0`` and promoting a
pre-release to its final release counts as a strictly-greater bump. Build
metadata (``+meta``) is ignored for precedence.

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


# A SemVer pre-release identifier is either a non-negative integer (compared
# numerically) or an ASCII alphanumeric/hyphen string (compared lexically). To
# get total ordering across the two kinds in a single tuple, each identifier is
# wrapped as ``(rank, value)``: rank 0 for numeric (sorts below all strings per
# SemVer rule 11.4.3), rank 1 for alphanumeric.
PreReleaseId = tuple[int, object]

# Full SemVer-comparable: ((major, minor, patch), is_release, prerelease_ids).
# ``is_release`` is True for a plain release and False for a pre-release; a
# release outranks any pre-release that shares its core (SemVer rule 11.3), and
# tuples compare element-by-element so ``True > False`` puts the release ahead.
# Build metadata is intentionally excluded: it does not affect precedence.
SemVer = tuple[tuple[int, int, int], bool, tuple[PreReleaseId, ...]]


def _valid_build_metadata(build: str) -> bool:
    """True when ``build`` is valid SemVer build metadata (rule 11/10).

    Build metadata is a dot-separated series of identifiers, each non-empty and
    drawn from ASCII alphanumerics and hyphen. Unlike pre-release identifiers,
    leading zeros are allowed. An empty string (a trailing ``+``) is invalid.
    """
    if not build:
        return False
    for ident in build.split("."):
        if not ident:
            return False
        if not ident.isascii() or not all(c.isalnum() or c == "-" for c in ident):
            return False
    return True


def _parse_prerelease(pre: str) -> tuple[PreReleaseId, ...] | None:
    """Parse a dot-separated pre-release string into comparable identifiers.

    Returns ``None`` when any identifier is empty or carries a character outside
    the SemVer alphabet (ASCII alphanumerics and hyphen). Numeric identifiers
    with leading zeros (other than ``0`` itself) are invalid per SemVer 11.
    """
    ids: list[PreReleaseId] = []
    for ident in pre.split("."):
        if not ident:
            return None
        if ident.isascii() and ident.isdigit():
            if len(ident) > 1 and ident.startswith("0"):
                return None
            ids.append((0, int(ident)))
            continue
        if not all(c.isalnum() or c == "-" for c in ident) or not ident.isascii():
            return None
        ids.append((1, ident))
    return tuple(ids)


def parse_version(value: str) -> SemVer | None:
    """Parse a SemVer 2.0.0 string into a comparable value, else ``None``.

    Requires exactly three numeric core identifiers (``MAJOR.MINOR.PATCH``).
    Honors pre-release precedence (a pre-release sorts below its release) and
    ignores build metadata. Returns ``None`` for anything that is not valid
    SemVer; the caller treats ``None`` as a configuration error. ``1``, ``1.2``,
    and ``1.2.3.4`` are rejected.
    """
    if not value or not value.strip():
        return None
    body, plus, build = value.strip().partition("+")
    # Build metadata does not affect precedence, but a trailing ``+`` or a
    # malformed identifier (``1.2.3+`` or ``1.2.3+a+b``) is invalid SemVer and
    # must be rejected, not silently dropped.
    if plus and not _valid_build_metadata(build):
        return None
    core, hyphen, pre = body.partition("-")
    parts = core.split(".")
    if len(parts) != 3:
        return None
    nums: list[int] = []
    for part in parts:
        if not part.isascii() or not part.isdigit():
            return None
        if len(part) > 1 and part.startswith("0"):  # no leading zeros
            return None
        nums.append(int(part))
    core_tuple = (nums[0], nums[1], nums[2])

    if not hyphen:
        # No hyphen: a plain release. Outranks any pre-release with same core.
        return (core_tuple, True, ())
    # A trailing hyphen with an empty pre-release body (``1.2.3-``) is invalid.
    prerelease = _parse_prerelease(pre)
    if prerelease is None:
        return None
    return (core_tuple, False, prerelease)


# --- Core check (pure) ---------------------------------------------------


def evaluate(
    changed_files: Iterable[str],
    version_pairs: dict[str, tuple[str | None | _BaseRefError, str | None]],
    plugins: Sequence[PluginManifest] = PLUGINS,
) -> tuple[list[Violation], list[str]]:
    """Pure core: decide violations from a changed set and version pairs.

    ``version_pairs`` maps a plugin manifest path to ``(old, new)``. ``old`` is
    the base-ref version string, ``None`` when the manifest did not exist at the
    base ref (a brand-new plugin, nothing to compare against), or a
    ``_BaseRefError`` when git could not read the base ref (a config error, not
    a new plugin). ``new`` is the disk version string, ``None`` when the
    manifest is missing or unreadable on disk now.

    Returns ``(violations, config_errors)``. ``config_errors`` is non-empty
    when a version string cannot be parsed or the base ref is unreadable; the
    CLI maps that to exit 2.
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

        if isinstance(old, _BaseRefError):
            config_errors.append(
                f"{plugin.manifest}: cannot read base version for "
                f"{plugin.name}: {old.message}"
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


# Sentinel for a git failure that is NOT "the path is absent at a valid ref".
# A bad base ref, a non-repo directory, or a git crash must surface as a config
# error, never collapse into the "new plugin, nothing to compare" pass path.
class _BaseRefError:
    """Marker: git could not read the base ref (distinct from path absence)."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


# git prints these when the *path* is absent at an otherwise valid ref. Any
# other non-zero exit means the *ref* itself is unusable (bad revision, not a
# repo), which is a config error rather than a new-plugin pass.
_PATH_ABSENT_MARKERS = (
    "does not exist",
    "exists on disk, but not in",
)


def _base_version(
    base_ref: str, manifest: str, repo_root: Path
) -> str | None | _BaseRefError:
    """Read the manifest version at ``base_ref`` via ``git show``.

    Returns the version string on success; ``None`` when the manifest did not
    exist at the base (a new plugin, nothing to compare); a ``_BaseRefError``
    when git itself failed (bad ref, non-repo, timeout). The caller maps the
    error to a config error so a broken base ref cannot masquerade as a new
    plugin and pass the gate.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{base_ref}:{manifest}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _BaseRefError(f"git show {base_ref}:{manifest} failed: {exc}")
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if any(marker in stderr for marker in _PATH_ABSENT_MARKERS):
            return None  # path absent at a valid ref: a new plugin
        return _BaseRefError(
            f"git show {base_ref}:{manifest} exit {proc.returncode}: {stderr}"
        )
    # git show succeeded: the manifest EXISTS at the base ref. If its content
    # cannot yield a version (invalid JSON, no version field, non-string
    # version), that is a malformed base manifest, a config error. Returning
    # None here would let evaluate treat an existing-but-broken base as a new
    # plugin and pass the gate.
    version = _read_version_text(proc.stdout)
    if version is None:
        return _BaseRefError(
            f"{base_ref}:{manifest} exists but has no readable version "
            "(invalid JSON or missing version field)"
        )
    return version


def _version_pairs(
    base_ref: str, repo_root: Path, plugins: Sequence[PluginManifest] = PLUGINS
) -> dict[str, tuple[str | None | _BaseRefError, str | None]]:
    """Build the ``(old, new)`` version map for every plugin manifest."""
    pairs: dict[str, tuple[str | None | _BaseRefError, str | None]] = {}
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
        # bumped is true only on a clean pass: no violations AND no config
        # errors. A config-error-only run exits 2; reporting bumped:true there
        # would let a downstream consumer read success from a failed run.
        "bumped": not violations and not config_errors,
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
