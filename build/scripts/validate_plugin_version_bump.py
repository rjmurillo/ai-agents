#!/usr/bin/env python3
"""Plugin manifest version-field gate.

Every packaged plugin in this repo is published from a source directory that
carries a ``.claude-plugin/plugin.json``. None of those manifests may carry a
``version`` field. This module fails when one does.

WHY THE FIELD MUST BE ABSENT
----------------------------

Claude Code resolves plugin freshness from the first of these that is set
(https://docs.claude.com/en/docs/claude-code/plugins-reference, section
"Version management", quoted verbatim):

    "The version is resolved from the first of these that is set:
       1. The version field in the plugin's plugin.json
       2. The version field in the plugin's marketplace entry in marketplace.json
       3. The git commit SHA of the plugin's source, for github, url,
          git-subdir, and relative-path sources in a git-hosted marketplace
       4. unknown, for npm sources or local directories not inside a git
          repository"

Both marketplace files in this repo list relative-path sources (``./.claude``,
``./src/claude``, ``./src/copilot-cli``) and neither carries a per-plugin
``version``. So with the field absent from plugin.json, every plugin resolves at
step 3: the git commit SHA, which changes on every merge. That is per-commit
freshness, which the hand-maintained counter this gate used to police could not
match.

Putting the field back switches Claude Code to step 1, where the same page says
of the explicit-version approach: "Users get updates only when you bump this
field. Pushing new commits without bumping it has no effect, and /plugin update
reports 'already at the latest version'." The field's presence also re-creates
the textual merge conflict that motivated this inversion: issue #4080 measured
14 of 22 conflicting PRs conflicting on nothing but this line.

GitHub Copilot CLI treats the field as optional metadata
(https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
lists ``name`` as the only required field and ``version`` under "Optional
metadata fields"). Its shipped bundle calls ``updatePlugin`` unconditionally
from ``updateAll``; the version string feeds display text and telemetry only.

ADR-091 records the decision and supersedes ADR-079.

RULE
----

A manifest listed in ``PLUGINS`` that exists at the validated ref MUST NOT carry
a ``version`` key. A manifest that does not exist at that ref is skipped: there
is nothing published to pin.

The check does not depend on what the diff touched. A version field is wrong
whether or not the plugin's source changed in this branch.

SCOPE
-----

Three packaged plugins (the only dirs with a ``.claude-plugin/plugin.json``):

    .claude/         -> .claude/.claude-plugin/plugin.json        (project-toolkit, Claude)
    src/claude/      -> src/claude/.claude-plugin/plugin.json     (claude-agents)
    src/copilot-cli/ -> src/copilot-cli/.claude-plugin/plugin.json (project-toolkit, Copilot)

``.github/`` and ``src/vs-code-agents/`` carry no plugin.json and are not
marketplace plugins, so they are out of scope.

The marketplace entries are resolution step 2 and must stay version-free for the
same reason, so this module checks them too. A marketplace-only change touches
no plugin source dir, so nothing else in CI would have read it: the pytest
workflow filters on Python paths and never fires on ``marketplace.json``.

    .claude-plugin/marketplace.json        (Claude marketplace)
    .github/plugin/marketplace.json        (Copilot marketplace)

CLI
---

::

    python3 build/scripts/validate_plugin_version_bump.py
    python3 build/scripts/validate_plugin_version_bump.py --head <sha>
    python3 build/scripts/validate_plugin_version_bump.py --format json

``--base`` and ``--files`` are still accepted so existing callers
(``scripts/validation/run_plugin_version_bump_ci.py``,
``scripts/validation/git_hook_policy.py``, ``scripts/validation/checks_plugin.py``)
keep working unchanged. They no longer affect the result: the presence of the
field is not a function of the diff.

EXIT CODES (per ADR-035)
------------------------

0 - no manifest or marketplace entry carries a version field
1 - one or more carry a version field
2 - configuration error (repo root absent, git unavailable, manifest malformed)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --- Plugin model --------------------------------------------------------


@dataclass(frozen=True)
class PluginManifest:
    """One packaged plugin: a source dir and the manifest that publishes it."""

    name: str
    source_dir: str  # posix prefix, no trailing slash
    manifest: str  # posix path to plugin.json (lives under source_dir)


# The three packaged plugins.
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


# The two marketplaces. A per-plugin ``version`` in an entry here is
# resolution step 2, which pins freshness ahead of the commit SHA exactly as a
# manifest version does.
MARKETPLACES: tuple[str, ...] = (
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
)


@dataclass(frozen=True)
class Violation:
    """One manifest or marketplace entry carrying a ``version`` it must not."""

    plugin: str
    manifest: str
    version: str
    reason: str  # "version-present" or "marketplace-version-present"


@dataclass(frozen=True)
class ManifestState:
    """A manifest as it stands at one git ref.

    ``exists`` is False when the path is absent at the ref. ``version`` is None
    when the manifest carries no ``version`` key, which is the required state.
    """

    exists: bool
    version: str | None


_ABSENT = ManifestState(exists=False, version=None)


# Sentinel for a git or parse failure that is NOT "the path is absent at a valid
# ref". A bad ref, a non-repo directory, or a malformed manifest must surface as
# a config error, never collapse into the "nothing published" pass path.
class _RefError:
    """Marker: the manifest could not be read at the ref."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


# git prints these when the *path* is absent at an otherwise valid ref. Any
# other non-zero exit means the *ref* itself is unusable (bad revision, not a
# repo), which is a config error rather than a nothing-published pass.
_PATH_ABSENT_MARKERS = (
    "does not exist",
    "exists on disk, but not in",
)

ManifestRead = ManifestState | _RefError


# --- Core check (pure) ---------------------------------------------------


def evaluate(
    states: Mapping[str, ManifestRead],
    plugins: Sequence[PluginManifest] = PLUGINS,
) -> tuple[list[Violation], list[str]]:
    """Pure core: decide violations from the manifest state at one ref.

    ``states`` maps a plugin manifest path to its ``ManifestState``, or to a
    ``_RefError`` when the manifest could not be read. A missing entry is itself
    a config error: the caller was asked about a plugin it never read.

    Returns ``(violations, config_errors)``. The CLI maps a non-empty
    ``config_errors`` to exit 2 and a non-empty ``violations`` to exit 1.
    """
    violations: list[Violation] = []
    config_errors: list[str] = []

    for plugin in plugins:
        state = states.get(plugin.manifest)

        if state is None:
            config_errors.append(
                f"{plugin.manifest}: no manifest state was read for {plugin.name}"
            )
            continue

        if isinstance(state, _RefError):
            config_errors.append(
                f"{plugin.manifest}: cannot read manifest for "
                f"{plugin.name}: {state.message}"
            )
            continue

        if not state.exists or state.version is None:
            continue

        violations.append(
            Violation(
                plugin=plugin.name,
                manifest=plugin.manifest,
                version=state.version,
                reason="version-present",
            )
        )

    return violations, config_errors


# --- I/O: git ------------------------------------------------------------


def _render_version(value: object) -> str:
    """Display form of a version value, which need not be a string to be wrong."""
    return value if isinstance(value, str) else repr(value)


def _state_from_text(text: str) -> ManifestRead:
    """Parse a plugin.json body into a ``ManifestState``, or a ``_RefError``."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        return _RefError(f"manifest is not valid JSON: {exc}")
    if not isinstance(data, dict):
        return _RefError("manifest is not a JSON object")
    if "version" not in data:
        return ManifestState(exists=True, version=None)
    return ManifestState(exists=True, version=_render_version(data["version"]))


def _show_at(ref: str, path: str, repo_root: Path) -> str | None | _RefError:
    """Return a file's text at ``ref``, None when absent, ``_RefError`` on failure.

    Reads from a git ref, not the working tree, so uncommitted edits cannot make
    the gate pass while the pushed commit still carries the field.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _RefError(f"git show {ref}:{path} failed: {exc}")
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if any(marker in stderr for marker in _PATH_ABSENT_MARKERS):
            return None  # path absent at a valid ref: nothing published
        return _RefError(f"git show {ref}:{path} exit {proc.returncode}: {stderr}")
    return proc.stdout


def _manifest_state_at(ref: str, manifest: str, repo_root: Path) -> ManifestRead:
    """Read a plugin manifest at ``ref`` and reduce it to a ``ManifestState``."""
    text = _show_at(ref, manifest, repo_root)
    if isinstance(text, _RefError):
        return text
    if text is None:
        return _ABSENT
    return _state_from_text(text)


def _marketplace_violations(text: str, path: str) -> tuple[list[Violation], list[str]]:
    """Return the version-carrying entries in one marketplace file."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        return [], [f"{path}: marketplace is not valid JSON: {exc}"]
    entries = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [], [f"{path}: marketplace has no plugins list"]
    found = [
        Violation(
            plugin=f"{entry.get('name', '<unnamed>')} (marketplace entry)",
            manifest=path,
            version=_render_version(entry["version"]),
            reason="marketplace-version-present",
        )
        for entry in entries
        if isinstance(entry, dict) and "version" in entry
    ]
    return found, []


def find_marketplace_violations(
    *,
    head_ref: str = "HEAD",
    repo_root: Path | None = None,
    marketplaces: Sequence[str] = MARKETPLACES,
) -> tuple[list[Violation], list[str]]:
    """Read every marketplace at ``head_ref`` and collect version-carrying entries."""
    root = repo_root or _REPO_ROOT
    violations: list[Violation] = []
    config_errors: list[str] = []
    for path in marketplaces:
        text = _show_at(head_ref, path, root)
        if isinstance(text, _RefError):
            config_errors.append(f"{path}: cannot read marketplace: {text.message}")
            continue
        if text is None:
            continue  # absent at this ref: nothing published
        found, errors = _marketplace_violations(text, path)
        violations.extend(found)
        config_errors.extend(errors)
    return violations, config_errors


def find_violations(
    *,
    head_ref: str = "HEAD",
    repo_root: Path | None = None,
    plugins: Sequence[PluginManifest] = PLUGINS,
) -> tuple[list[Violation], list[str]]:
    """Read every plugin manifest at ``head_ref``, then run ``evaluate``."""
    root = repo_root or _REPO_ROOT
    states: dict[str, ManifestRead] = {
        plugin.manifest: _manifest_state_at(head_ref, plugin.manifest, root)
        for plugin in plugins
    }
    violations, config_errors = evaluate(states, plugins)
    market_violations, market_errors = find_marketplace_violations(
        head_ref=head_ref, repo_root=root
    )
    return violations + market_violations, config_errors + market_errors


# --- Output --------------------------------------------------------------


_FIX = (
    "Fix: delete the `version` line from each manifest above. Claude Code "
    "resolves freshness from the git commit SHA when the field is absent, which "
    "is per-commit and needs no hand bump. A committed version pins freshness to "
    "that string and conflicts across every concurrent PR (ADR-091, issue #4080)."
)


def _format_text(violations: Sequence[Violation], config_errors: Sequence[str]) -> str:
    if config_errors and not violations:
        lines = ["plugin-version-bump: CONFIG ERROR"]
        lines.extend(f"  {e}" for e in config_errors)
        return "\n".join(lines)
    if not violations:
        return "plugin-version-bump: OK"
    lines = ["plugin-version-bump: VERSION FIELD PRESENT"]
    for v in violations:
        lines.append("")
        lines.append(f"  [{v.reason}] {v.plugin}")
        lines.append(f"    file:     {v.manifest}")
        lines.append(f"    version:  {v.version}")
    lines.append("")
    lines.append(_FIX)
    if config_errors:
        lines.append("")
        lines.append("Config errors:")
        lines.extend(f"  {e}" for e in config_errors)
    return "\n".join(lines)


def _format_json(violations: Sequence[Violation], config_errors: Sequence[str]) -> str:
    payload = {
        # version_free is true only on a clean pass: no violations AND no config
        # errors. A config-error-only run exits 2; reporting version_free:true
        # there would let a downstream consumer read success from a failed run.
        "version_free": not violations and not config_errors,
        "violations": [
            {
                "plugin": v.plugin,
                "manifest": v.manifest,
                "version": v.version,
                "reason": v.reason,
            }
            for v in violations
        ],
        "config_errors": list(config_errors),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


# --- CLI -----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Fail when a packaged plugin manifest or marketplace entry "
            "carries a version field."
        ),
    )
    p.add_argument(
        "--base",
        default="origin/main",
        help="Accepted for caller compatibility and ignored. The field's "
        "presence does not depend on the diff.",
    )
    p.add_argument(
        "--head",
        default="HEAD",
        help="Git ref to read the manifests from (default: HEAD).",
    )
    p.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Accepted for caller compatibility and ignored.",
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

    violations, config_errors = find_violations(
        head_ref=args.head, repo_root=repo_root
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
